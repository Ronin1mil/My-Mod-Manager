import json
import tempfile
import unittest
from pathlib import Path

from modmanager import order as order_mod
from modmanager import scan
from modmanager.descriptor import parse_descriptor, parse_metadata
from modmanager.library import Library
from modmanager import games
from modmanager.server import GameApp
from modmanager.store import Store, write_load_file

DESC = '''version="1.0"
tags={
\t"Gameplay" "Utilities"
}
name="Test # Mod"
dependencies={ "Base Mod" }
replace_path="common/goods"
supported_version="1.7.*"
path="mod/{}"
'''


def mk(root, name, files, desc=None, meta=None):
    d = Path(root) / "mod" / name
    for rel, txt in files.items():
        (d / rel).parent.mkdir(parents=True, exist_ok=True)
        (d / rel).write_text(txt)
    if meta is not None:
        (d / ".metadata").mkdir(parents=True, exist_ok=True)
        (d / ".metadata/metadata.json").write_text(json.dumps(meta))
    (Path(root) / "mod" / f"{name}.mod").write_text(desc or f'name="{name}"\npath="mod/{name}"\n')


class T(unittest.TestCase):
    def test_parse(self):
        d = parse_descriptor(DESC)
        self.assertEqual(d["tags"], ["Gameplay", "Utilities"])
        self.assertEqual(d["dependencies"], ["Base Mod"])
        self.assertEqual(d["replace_path"], ["common/goods"])
        self.assertEqual(d["name"], "Test # Mod")

    def test_parse_metadata(self):
        d = parse_metadata(json.dumps({
            "name": "M", "version": "2", "supported_game_version": "1.7.*", "tags": ["Gameplay"],
            "relationships": [{"rel_type": "dependency", "display_name": "Base", "id": "123"}],
            "game_custom_data": {"multiplayer_synchronized": False, "replace_paths": ["common/x"]}}))
        self.assertEqual(d["dependencies"], ["Base"])
        self.assertEqual(d["replace_path"], ["common/x"])
        self.assertIs(d["multiplayer_synchronized"], False)
        self.assertEqual(parse_metadata("not json"), {})

    def test_top_level_keys(self):
        t = "# c\ntrait_a = { x = { y = 1 } }\nREPLACE:b={}\nINJECT:c = { }\n@v = 3\n"
        self.assertEqual(scan.top_level_keys(t), [("trait_a", None), ("b", "REPLACE"), ("c", "INJECT")])

    def test_loc_keys(self):
        t = 'l_english:\n foo_key:0 "Hello"\n bar:1 "x"\n'
        self.assertEqual(scan.loc_keys(t), [("l_english", "foo_key"), ("l_english", "bar")])

    def test_conflicts_and_deps(self):
        with tempfile.TemporaryDirectory() as r:
            mk(r, "A", {"common/goods/a.txt": "g1 = { }", "events/e.txt": "x = {}",
                        "localization/english/a_l_english.yml": 'l_english:\n k1:0 "a"\n'})
            mk(r, "B", {"common/goods/b.txt": "g1 = { }", "events/e.txt": "y = {}",
                        "localization/english/b_l_english.yml": 'l_english:\n k1:0 "b"\n'},
               'name="B"\npath="mod/B"\ndependencies={ "Z" "A" }\nsupported_version="1.6.*"\n')
            mods = scan.scan_mods(r)
            order = ["local:B", "local:A"]
            c = scan.find_conflicts(mods, order)
            kinds = {(x["kind"], x["path"]) for x in c}
            self.assertIn(("file", "events/e.txt"), kinds)
            self.assertIn(("definition", "common/goods: g1"), kinds)
            self.assertIn(("localization", "l_english: k1"), kinds)
            self.assertEqual([x for x in c if x["kind"] == "file"][0]["winner"], "local:A")
            res = order_mod.compute_order(mods, order, auto=False, game_version="1.7.6")
            codes = {(i["code"], i["module"]) for i in res["issues"]}
            self.assertIn(("missing_dependency", "local:B"), codes)
            self.assertIn(("wrong_order", "local:B"), codes)
            self.assertIn(("version_mismatch", "local:B"), codes)

    def test_replace_and_inject(self):
        with tempfile.TemporaryDirectory() as r:
            mk(r, "A", {"common/goods/a.txt": "g1 = { }"})
            mk(r, "B", {"common/goods/b.txt": "INJECT:g1 = { }"})
            mk(r, "C", {"common/goods/c.txt": "REPLACE:g1 = { }"}, meta={
                "name": "C", "game_custom_data": {"replace_paths": ["common/goods"]}})
            mods = scan.scan_mods(r)
            c = scan.find_conflicts(mods, ["local:A", "local:B", "local:C"])
            by = {(x["kind"], x["mods"][-1]): x for x in c}
            defs = [x for x in c if x["kind"] == "definition"]
            self.assertEqual(len(defs), 1)
            self.assertEqual(defs[0]["mods"], ["local:A", "local:C"])  # INJECT isn't a clash
            self.assertEqual(defs[0]["severity"], "info")              # REPLACE winner is intentional
            rep = by[("replace", "local:C")]
            self.assertEqual(rep["mods"], ["local:A", "local:B", "local:C"])

    def test_store_share_and_export(self):
        with tempfile.TemporaryDirectory() as r:
            mk(r, "A", {"x.txt": ""})
            ws = Path(r) / "ws" / "999"
            (ws / ".metadata").mkdir(parents=True)
            (ws / ".metadata/metadata.json").write_text('{"name": "WS Mod"}')
            mods = scan.scan_mods(r, Path(r) / "ws")
            self.assertEqual(mods["ws:999"]["name"], "WS Mod")
            s = Store(Path(r) / "p.json")
            pid = s.create("p", ["local:A", "ws:999"])
            s.update(pid, disabled=["local:A"])
            self.assertEqual(Store(Path(r) / "p.json").get(pid)["disabled"], ["local:A"])
            nid = s.duplicate(pid, "c")
            self.assertEqual(s.get(nid)["disabled"], ["local:A"])
            s.update(pid, notes="n", launch_args=["-debug_mode"])
            iid, missing = s.import_shared(s.share(pid, mods), mods)
            self.assertEqual((s.get(iid)["mods"], s.get(iid)["disabled"], missing),
                             (["local:A", "ws:999"], ["local:A"], []))
            self.assertEqual((s.get(iid)["notes"], s.get(iid)["launch_args"]), ("n", ["-debug_mode"]))
            for bad in ({"format": "modmanager-playset", "mods": "x"},
                        {"format": "modmanager-playset", "mods": [], "launch_args": ["; rm -rf /"]}):
                with self.assertRaises(ValueError):
                    s.import_shared(bad, mods)
            self.assertEqual(len(s.data["playsets"]), 3)  # failed imports leave nothing behind
            with self.assertRaises(ValueError):
                s.import_shared({"nope": 1}, mods)
            s.update(pid, disabled=[])
            (Path(r) / "content_load.json").write_text('{"enabled_mods": ["old"], "disabled_dlcs": ["x"]}')
            f = write_load_file(games.VIC3, r, mods, s.export(pid, mods))
            d = json.loads(f.read_text())
            self.assertEqual(d["enabled_mods"], ["mod/A.mod", "mod/ugc_999.mod"])
            self.assertEqual(d["disabled_dlcs"], ["x"])
            self.assertTrue((Path(r) / "content_load.json.bak").is_file())
            self.assertIn('remote_file_id="999"', (Path(r) / "mod/ugc_999.mod").read_text())

    def test_app_analyse(self):
        with tempfile.TemporaryDirectory() as r:
            mk(r, "A", {"events/e.txt": "x = {}"})
            mk(r, "B", {"events/e.txt": "y = {}"})
            app = GameApp(games.VIC3, user_dir=r, workshop_dir=Path(r) / "none", game_version_="1.7.6",
                          store=Store(Path(r) / "p.json"), library=Library(Path(r) / "lib.json"), autodetect=False)
            pid = app.store.create("p", ["local:A", "local:B"])
            res = app.analyse(pid)
            self.assertEqual(res["counts"], {"file": 1})


if __name__ == "__main__":
    unittest.main()
