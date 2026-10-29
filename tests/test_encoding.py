"""Windows reads text files in the local code page unless told otherwise (cp1252 on most PCs). Everything the app
reads or writes as text must name its encoding, or a name like "Ünïcödé — 日本語" breaks only on Windows."""
import ast
import json
import tempfile
import unittest
from pathlib import Path

from modmanager import games, presets
from modmanager.store import Store, ensure_descriptor_stub

SRC = Path(__file__).resolve().parent.parent / "modmanager"


def text_io_without_encoding(path):
    """Calls in a source file that read or write text without naming the encoding (binary opens are fine)."""
    out = []
    for n in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if not isinstance(n, ast.Call):
            continue
        fn = n.func
        name = fn.attr if isinstance(fn, ast.Attribute) else getattr(fn, "id", "")
        kws = {k.arg for k in n.keywords}
        if name in ("read_text", "write_text") and "encoding" not in kws:
            out.append(f"{path.name}:{n.lineno}: {name}()")
        elif name == "open" and isinstance(fn, ast.Name):
            mode = next((a.value for a in n.args[1:2] if isinstance(a, ast.Constant)), None) or \
                next((k.value.value for k in n.keywords if k.arg == "mode" and isinstance(k.value, ast.Constant)), "r")
            if "b" not in str(mode) and "encoding" not in kws:
                out.append(f"{path.name}:{n.lineno}: open(mode={mode!r})")
    return out


class Source(unittest.TestCase):
    def test_every_text_read_and_write_names_its_encoding(self):
        bad = [x for f in sorted(SRC.glob("*.py")) for x in text_io_without_encoding(f)]
        self.assertEqual(bad, [], "text I/O without an explicit encoding (breaks on Windows with non-ASCII text)")

    def test_the_check_itself_catches_a_bad_call(self):
        with tempfile.TemporaryDirectory() as d:
            f = Path(d) / "x.py"
            f.write_text("from pathlib import Path\nPath('a').read_text()\nopen('b', 'w')\nopen('c', 'rb')\nPath('d').write_text('x', encoding='utf-8')\n", encoding="utf-8")
            self.assertEqual(len(text_io_without_encoding(f)), 2)


class Behaviour(unittest.TestCase):
    NAME = "Ünïcödé — 日本語 ☃"

    def test_the_built_in_presets_are_utf8(self):
        for f in Path(presets.BUILTIN).glob("*.json"):
            f.read_bytes().decode("utf-8")

    def test_unicode_names_survive_the_playset_file_and_descriptor_stubs(self):
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            st = Store(d / "p.json")
            pid = st.create(self.NAME, [])
            self.assertEqual(Store(d / "p.json").get(pid)["name"], self.NAME)
            m = {"source": "workshop", "name": self.NAME, "root": str(d / "ws/123"), "remote_id": "123", "id": "ws:123"}
            self.assertTrue(ensure_descriptor_stub(games.CK3, d, m))
            stub = (d / "mod/ugc_123.mod").read_bytes().decode("utf-8")  # the game reads it as UTF-8
            self.assertIn(self.NAME, stub)

    def test_preset_with_unicode_roundtrips(self):
        with tempfile.TemporaryDirectory() as d:
            doc = {"format": presets.FORMAT, "id": "uni", "game": "ck3", "name": self.NAME, "status": "unverified",
                   "description": "é — ☃", "source": "", "mods": [{"workshop_id": "1", "name": self.NAME}]}
            p = Path(d) / "uni.json"
            p.write_text(json.dumps(doc, ensure_ascii=False), encoding="utf-8")
            self.assertEqual(json.loads(p.read_text(encoding="utf-8"))["name"], self.NAME)


if __name__ == "__main__":
    unittest.main()
