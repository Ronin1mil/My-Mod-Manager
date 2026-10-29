"""Fuzz and robustness tests: hostile or broken input must raise a clean error or be tolerated, never crash,
hang or write outside the intended folder."""
import io
import json
import os
import random
import string
import tempfile
import unittest
from unittest import mock
import zipfile
from pathlib import Path

from modmanager import install, launch, scan
from modmanager.descriptor import parse_descriptor, parse_metadata
from modmanager.store import Store

ALPHABET = string.printable + '{}="#\\:@\u00e9\u4e2d\x00\ufeff'


def rnd_text(rng, n):
    return "".join(rng.choice(ALPHABET) for _ in range(n))


class Parsers(unittest.TestCase):
    def test_random_text_never_crashes_parsers(self):
        rng = random.Random(1)
        for _ in range(1500):
            t = rnd_text(rng, rng.randint(0, 300))
            parse_descriptor(t)
            scan.top_level_keys(t)
            scan.loc_keys(t)
            parse_metadata(t)

    def test_structured_garbage(self):
        for t in ("{", "}", "{{{{", "}}}}", "a = ", "a = {", "= = =", 'name="unterminated', "a={b={c={}}}" * 2000,
                  "\n".join(f"k{i} = {{" for i in range(500)), '"' * 999, "#" * 10000, "a=" + "{" * 5000):
            parse_descriptor(t)
            scan.top_level_keys(t)

    def test_metadata_wrong_types_are_tolerated(self):
        for d in ([], "x", 5, None, {"name": 5, "tags": "x", "relationships": 5}, {"relationships": [1, None, "x"]},
                  {"game_custom_data": []}, {"tags": [1, {"a": 1}], "name": ["x"]}, {"game_custom_data": {"replace_paths": 5}}):
            try:
                out = parse_metadata(json.dumps(d))
            except (TypeError, AttributeError) as e:
                self.fail(f"{d!r}: {e!r}")
            self.assertIsInstance(out, dict)

    def test_top_level_keys_handles_big_input_quickly(self):
        import time
        t = "\n".join(f"key_{i} = {{ a = {{ b = {i} }} }}" for i in range(40000))
        s = time.time()
        self.assertEqual(len(scan.top_level_keys(t)), 40000)
        self.assertLess(time.time() - s, 5)

    def test_launch_arg_validation_fuzz(self):
        rng = random.Random(2)
        for _ in range(2000):
            a = rnd_text(rng, rng.randint(0, 20))
            try:
                out = launch.validate_launch_args([a])
            except ValueError:
                continue
            for x in out:  # whatever is accepted must be shell-inert
                self.assertRegex(x, r"^[-/][A-Za-z0-9_.:/=\-]{1,63}$")


class Imports(unittest.TestCase):
    def test_random_json_import_only_raises_valueerror(self):
        rng = random.Random(3)

        def val(depth=0):
            c = rng.randint(0, 6 if depth < 3 else 3)
            return [None, True, rng.randint(-5, 5), rnd_text(rng, 5), {"a": 1}][c] if c < 4 else \
                ([val(depth + 1) for _ in range(rng.randint(0, 3))] if c < 6 else
                 {rnd_text(rng, 3): val(depth + 1) for _ in range(rng.randint(0, 3))})

        with tempfile.TemporaryDirectory() as r:
            s = Store(Path(r) / "p.json")
            for _ in range(1500):
                doc = {"format": "modmanager-playset", "version": 1, "name": val(), "mods": val(), "notes": val(),
                       "launch_args": val(), "auto_sort": val()}
                if rng.random() < .3:
                    doc["mods"] = [{"name": val(), "remote_id": val(), "enabled": val()} for _ in range(rng.randint(0, 4))]
                try:
                    s.import_shared(doc, {})
                except ValueError:
                    pass
            for ps in s.data["playsets"].values():  # whatever got through is fully valid
                self.assertTrue(0 < len(ps["name"]) <= 60)
                self.assertIsInstance(ps["auto_sort"], bool)
                launch.validate_launch_args(ps["launch_args"])

    def test_store_survives_corrupt_state_file_by_failing_clearly(self):
        with tempfile.TemporaryDirectory() as r:
            p = Path(r) / "p.json"
            p.write_text("{broken")
            with self.assertRaises(ValueError):
                Store(p)
            p.write_text(json.dumps({"active": "x", "playsets": {"x": {"id": "x", "name": "n", "mods": ["a"],
                                                                        "disabled": []}}, "settings": {}}))
            ps = Store(p).get("x")  # playset saved by an older version: defaults filled in
            self.assertEqual((ps["notes"], ps["auto_sort"], ps["separate_saves"]), ("", True, False))


class Archives(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.r = Path(self.tmp.name)
        _p = mock.patch.dict(os.environ, {"MODMANAGER_CONFIG_DIR": str(self.r / "cfg")})
        _p.start()
        self.addCleanup(_p.stop)

    def tearDown(self):
        self.tmp.cleanup()

    def snapshot(self):
        return {p for p in self.r.rglob("*") if "cfg" not in p.parts}

    def test_safe_relative_fuzz_never_escapes(self):
        rng = random.Random(4)
        pieces = ["..", ".", "a", "b.txt", "/", "\\", "C:", "\x00", "CON", "nul.txt", "x:y", " ", "..\\", "%2e%2e", "é"]
        for _ in range(5000):
            name = "".join(rng.choice(pieces) for _ in range(rng.randint(1, 8)))
            try:
                rel = install.safe_relative(name)
            except install.UnsafeArchive:
                continue
            self.assertFalse(rel.startswith("/"), name)
            self.assertNotIn("..", rel.split("/"), name)
            self.assertNotRegex(rel, r"^[A-Za-z]:", name)
            self.assertNotIn("\\", rel)

    def test_mutated_zips_fail_cleanly_and_write_nothing_outside(self):
        base = io.BytesIO()
        with zipfile.ZipFile(base, "w", zipfile.ZIP_DEFLATED) as z:
            z.writestr("M/.metadata/metadata.json", '{"name": "M"}')
            for i in range(5):
                z.writestr(f"M/common/f{i}.txt", "x = {}\n" * 50)
        raw = base.getvalue()
        rng = random.Random(5)
        before = self.snapshot()
        for i in range(400):
            b = bytearray(raw)
            for _ in range(rng.randint(1, 12)):
                b[rng.randrange(len(b))] = rng.randrange(256)
            if rng.random() < .3:
                b = b[:rng.randrange(len(b))]
            p = self.r / "f.zip"
            p.write_bytes(bytes(b))
            user = self.r / f"user{i}"
            try:
                install.install_archive(p, user, "f.zip")
            except ValueError:
                pass  # includes UnsafeArchive
            except Exception as e:  # noqa: BLE001
                self.fail(f"iteration {i}: unexpected {type(e).__name__}: {e}")
        # nothing was ever written outside user dirs / config
        outside = {p for p in self.snapshot() - before if not any(part.startswith("user") for part in p.parts)
                   and p.name != "f.zip"}
        self.assertEqual(outside, set())

    def test_many_hostile_names_in_one_archive_are_all_rejected(self):
        hostile = ["../../evil.txt", "..\\..\\evil.txt", "/abs/evil.txt", "C:\\evil.txt", "M/../../evil.txt",
                   "M/aux.txt", "M/x.dll", "M/x.EXE", "M/x.Bat", "M/x:stream"]
        for h in hostile:
            p = self.r / "h.zip"
            with zipfile.ZipFile(p, "w") as z:
                z.writestr("M/.metadata/metadata.json", '{"name": "M"}')
                z.writestr(h, "x")
            with self.assertRaises(ValueError, msg=h):
                install.install_archive(p, self.r / "user", "h.zip")
        self.assertFalse((self.r / "evil.txt").exists())
        self.assertFalse((self.r / "user/mod/M").exists())


class ScanRobustness(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.r = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_broken_mods_do_not_break_the_scan(self):
        mod = self.r / "mod"
        mod.mkdir()
        (mod / "bad.mod").write_bytes(b"\xff\xfe\x00garbage\x00\x00")
        (mod / "empty.mod").write_text("")
        (mod / "nopath.mod").write_text('name="NoPath"\n')
        (mod / "gone.mod").write_text('name="Gone"\npath="mod/does-not-exist"\n')
        (mod / "abs.mod").write_text(f'name="Abs"\npath="{self.r}/elsewhere"\n')
        d = mod / "brokenmeta"
        (d / ".metadata").mkdir(parents=True)
        (d / ".metadata/metadata.json").write_text("{not json")
        (mod / "brokenmeta.mod").write_text('name="BM"\npath="mod/brokenmeta"\n')
        (self.r / "elsewhere/common").mkdir(parents=True)
        mods = scan.scan_mods(self.r)
        self.assertTrue(mods["local:gone"]["exists"] is False)
        self.assertTrue(mods["local:abs"]["exists"])
        self.assertEqual(mods["local:brokenmeta"]["name"], "BM")
        # and the conflict scanner copes with all of them
        scan.find_conflicts(mods, list(mods))

    def test_binary_and_huge_text_files_in_mods(self):
        m = self.r / "mod/M/common/goods"
        m.mkdir(parents=True)
        (m / "bin.txt").write_bytes(bytes(range(256)) * 100)
        (m / "bom.txt").write_bytes(b"\xef\xbb\xbfgood_a = { }\n")
        (self.r / "mod/M.mod").write_text('name="M"\npath="mod/M"\n')
        (self.r / "mod/N/common/goods").mkdir(parents=True)
        (self.r / "mod/N/common/goods/n.txt").write_text("good_a = { }\n")
        (self.r / "mod/N.mod").write_text('name="N"\npath="mod/N"\n')
        c = scan.find_conflicts(scan.scan_mods(self.r), ["local:M", "local:N"])
        self.assertIn(("definition", "common/goods: good_a"), {(x["kind"], x["path"]) for x in c})  # BOM tolerated

    @unittest.skipIf(os.name == "nt", "symlinks need privileges on Windows")
    def test_symlinks_inside_a_mod_are_not_followed(self):
        outside = self.r / "outside"
        outside.mkdir()
        (outside / "secret.txt").write_text("x = {}")
        m = self.r / "mod/M"
        (m / "common").mkdir(parents=True)
        (m / "common/link").symlink_to(outside, target_is_directory=True)
        (m / "common/loop").symlink_to(m, target_is_directory=True)
        (m / "common/file.txt").symlink_to(outside / "secret.txt")
        (self.r / "mod/M.mod").write_text('name="M"\npath="mod/M"\n')
        files = scan.list_files(m)
        self.assertEqual(files, {})  # links are ignored, no loops, no escaping the mod folder

    def test_replace_path_semantics(self):
        def mk(name, files, replace=()):
            d = self.r / "mod" / name
            for rel in files:
                (d / rel).parent.mkdir(parents=True, exist_ok=True)
                (d / rel).write_text("a = {}")
            (self.r / "mod" / f"{name}.mod").write_text(f'name="{name}"\npath="mod/{name}"\n' +
                                                      "".join(f'replace_path="{p}"\n' for p in replace))
        mk("A", ["common/goods/a.txt", "common/other/o.txt"])
        mk("R", ["common/goods/r.txt"], replace=["common/goods"])
        mk("Late", ["common/goods/l.txt"])
        mods = scan.scan_mods(self.r)
        rep = [x for x in scan.find_conflicts(mods, ["local:A", "local:R", "local:Late"]) if x["kind"] == "replace"]
        self.assertEqual(len(rep), 1)
        self.assertEqual(rep[0]["mods"], ["local:A", "local:R"])  # only mods loaded BEFORE are wiped
        self.assertIn("1 files", rep[0]["path"])
        # replacer loading first wipes nothing
        self.assertEqual([x for x in scan.find_conflicts(mods, ["local:R", "local:A"]) if x["kind"] == "replace"], [])


if __name__ == "__main__":
    unittest.main()
