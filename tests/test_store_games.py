"""Playset storage, sharing, load files per game, and moving over from the standalone managers."""
import json
import os
import tempfile
import threading
import unittest
from pathlib import Path
from unittest import mock

from modmanager import games, scan
from modmanager.server import GameApp
from modmanager.store import GlobalSettings, Store, mod_entry, write_load_file
from tests.helpers import ALL, mkmod, mkworkshop

L = lambda *n: [f"local:{x}" for x in n]


class Base(unittest.TestCase):
    def setUp(self):
        self.t = tempfile.TemporaryDirectory()
        self.r = Path(self.t.name)
        self.addCleanup(self.t.cleanup)
        p = mock.patch.dict(os.environ, {"MODMANAGER_CONFIG_DIR": str(self.r / "cfg"), "XDG_CONFIG_HOME": str(self.r / "xdg")})
        p.start()
        self.addCleanup(p.stop)


class LoadFiles(Base):
    def setUp(self):
        super().setUp()
        self.user = self.r / "user"
        mkmod(self.user, "A")
        mkmod(self.user, "My Mod (v2)")
        mkworkshop(self.r / "ws", 123, "WS Mod")
        self.mods = scan.scan_mods(self.user, self.r / "ws")

    def test_each_game_writes_its_own_file_name(self):
        for g in ALL:
            f = write_load_file(g, self.user, self.mods, ["local:A"])
            self.assertEqual(f.name, g.load_file)
            self.assertTrue((self.user / g.load_file).is_file())

    def test_descriptor_style_lists_mod_stubs_and_creates_missing_workshop_stub(self):
        for g in (games.CK3, games.VIC3):
            (self.user / "mod/ugc_123.mod").unlink() if (self.user / "mod/ugc_123.mod").exists() else None
            f = write_load_file(g, self.user, self.mods, ["local:A", "ws:123", "local:My Mod (v2)"])
            self.assertEqual(json.loads(f.read_text())["enabled_mods"],
                             ["mod/A.mod", "mod/ugc_123.mod", "mod/My Mod (v2).mod"], g.id)
            stub = (self.user / "mod/ugc_123.mod").read_text()
            self.assertIn('remote_file_id="123"', stub)
            self.assertIn(str(self.r / "ws" / "123").replace("\\", "/"), stub)

    def test_path_style_lists_local_folders_and_workshop_paths_and_writes_no_stubs(self):
        f = write_load_file(games.EU5, self.user, self.mods, ["local:A", "ws:123"])
        self.assertEqual(json.loads(f.read_text())["enabled_mods"], ["mod/A", str(self.r / "ws/123")])
        self.assertFalse((self.user / "mod/ugc_123.mod").exists())

    def test_existing_settings_survive_and_old_file_is_backed_up(self):
        (self.user / "dlc_load.json").write_text(json.dumps({"disabled_dlcs": ["dlc001"], "x": 1, "enabled_mods": ["old"]}))
        f = write_load_file(games.CK3, self.user, self.mods, ["local:A"])
        got = json.loads(f.read_text())
        self.assertEqual((got["disabled_dlcs"], got["x"], got["enabled_mods"]), (["dlc001"], 1, ["mod/A.mod"]))
        self.assertEqual(json.loads((self.user / "dlc_load.json.bak").read_text())["enabled_mods"], ["old"])

    def test_damaged_or_odd_existing_file_is_replaced(self):
        for junk in ("{not json", "[]", '"x"', ""):
            (self.user / "dlc_load.json").write_text(junk)
            f = write_load_file(games.CK3, self.user, self.mods, ["local:A"])
            self.assertEqual(json.loads(f.read_text())["enabled_mods"], ["mod/A.mod"], junk)

    def test_order_is_exactly_the_given_order_and_no_temp_files_remain(self):
        ids = ["local:My Mod (v2)", "ws:123", "local:A"]
        f = write_load_file(games.VIC3, self.user, self.mods, ids)
        self.assertEqual(len(json.loads(f.read_text())["enabled_mods"]), 3)
        self.assertEqual([p.name for p in self.user.iterdir() if p.suffix == ".tmp"], [])

    def test_mod_entry_per_style(self):
        m = self.mods["local:A"]
        self.assertEqual(mod_entry(games.CK3, m), "mod/A.mod")
        self.assertEqual(mod_entry(games.EU5, m), "mod/A")


class StoreBasics(Base):
    def test_validation_and_atomic_update(self):
        s = Store(self.r / "p.json")
        pid = s.create("p", L("A", "B", "A"))
        self.assertEqual(s.get(pid)["mods"], L("A", "B"))
        before = json.loads(json.dumps(s.get(pid)))
        for bad in ({"mods": "x"}, {"mods": [1]}, {"name": ""}, {"name": "x" * 99}, {"notes": 5},
                    {"auto_sort": "yes"}, {"launch_args": ["nope"]}):
            with self.assertRaises(ValueError, msg=bad):
                s.update(pid, **{"name": "changed", **bad})
            self.assertEqual(s.get(pid), before)  # nothing half-applied

    def test_rolling_backup_and_no_temp_leftovers(self):
        p = self.r / "p.json"
        s = Store(p)
        pid = s.create("one")
        s.update(pid, name="two")
        self.assertEqual(json.loads(p.with_suffix(".bak").read_text())["playsets"][pid]["name"], "one")
        self.assertEqual([f.name for f in self.r.iterdir() if f.suffix == ".tmp"], [])

    def test_damaged_file_is_never_overwritten(self):
        p = self.r / "p.json"
        p.write_text("{broken")
        with self.assertRaises(ValueError) as e:
            Store(p)
        self.assertIn("damaged", str(e.exception))
        self.assertEqual(p.read_text(), "{broken")
        p.write_text("[1, 2]")
        with self.assertRaises(ValueError):
            Store(p)

    def test_delete_active_picks_another(self):
        s = Store(self.r / "p.json")
        a, b = s.create("a"), s.create("b")
        s.delete(a)
        self.assertEqual(s.data["active"], b)
        s.delete(b)
        self.assertIsNone(s.data["active"])

    def test_duplicate_is_independent(self):
        s = Store(self.r / "p.json")
        pid = s.create("p", L("A", "B"), L("B"), notes="n", launch_args=["-debug_mode"])
        nid = s.duplicate(pid, "copy")
        s.update(nid, mods=L("B", "A"))
        self.assertEqual((s.get(pid)["mods"], s.get(nid)["disabled"], s.get(nid)["notes"]), (L("A", "B"), L("B"), "n"))

    def test_per_game_settings_validation(self):
        s = Store(self.r / "p.json")
        self.assertEqual(s.settings()["include_vanilla"], True)
        s.update_settings(game_dir="/x", include_vanilla=False)
        self.assertEqual(Store(self.r / "p.json").settings()["game_dir"], "/x")
        for bad in ({"nope": 1}, {"game_dir": 5}, {"include_vanilla": "no"}, {"user_dir": "x" * 2000}):
            with self.assertRaises(ValueError):
                s.update_settings(**bad)
        self.assertFalse(s.settings()["include_vanilla"])

    def test_global_settings(self):
        g = GlobalSettings(self.r / "g.json")
        self.assertEqual(g.get(), {"auto_update_check": False, "dismissed_update": "", "last_game": "", "fetch_logos": True})
        g.update(last_game="eu5")
        self.assertEqual(GlobalSettings(self.r / "g.json").get()["last_game"], "eu5")
        for bad in ({"x": 1}, {"auto_update_check": "y"}, {"last_game": "z" * 50}):
            with self.assertRaises(ValueError):
                g.update(**bad)
        (self.r / "g.json").write_text("garbage")
        self.assertFalse(GlobalSettings(self.r / "g.json").get()["auto_update_check"])  # damaged -> defaults

    def test_parallel_saves_never_corrupt_the_file(self):
        s = Store(self.r / "p.json")
        pid = s.create("p")
        lock = threading.Lock()
        errs = []

        def work(i):
            for j in range(20):
                try:
                    with lock:  # the server serialises requests the same way
                        s.update(pid, mods=L("A", "B") if (i + j) % 2 else L("B", "A"))
                except Exception as e:  # pragma: no cover
                    errs.append(e)
        ts = [threading.Thread(target=work, args=(i,)) for i in range(6)]
        [t.start() for t in ts]
        [t.join() for t in ts]
        self.assertEqual(errs, [])
        self.assertIn(json.loads((self.r / "p.json").read_text())["playsets"][pid]["mods"], (L("A", "B"), L("B", "A")))


class Sharing(Base):
    def setUp(self):
        super().setUp()
        mkmod(self.r / "u", "A")
        mkmod(self.r / "u", "B")
        mkworkshop(self.r / "ws", 77, "Shared WS")
        self.mods = scan.scan_mods(self.r / "u", self.r / "ws")
        self.s = Store(self.r / "p.json")

    def test_roundtrip_keeps_order_disabled_and_settings(self):
        pid = self.s.create("p", ["local:B", "ws:77", "local:A"], ["ws:77"], notes="hi", launch_args=["-debug_mode"])
        doc = json.loads(json.dumps(self.s.share(pid, self.mods, "ck3")))
        self.assertEqual((doc["format"], doc["game"]), ("modmanager-playset", "ck3"))
        nid, missing = self.s.import_shared(doc, self.mods, "ck3")
        ps = self.s.get(nid)
        self.assertEqual((ps["mods"], ps["disabled"], ps["notes"], ps["launch_args"], missing),
                         (["local:B", "ws:77", "local:A"], ["ws:77"], "hi", ["-debug_mode"], []))

    def test_workshop_id_beats_name_and_missing_are_reported(self):
        doc = {"format": "modmanager-playset", "game": "ck3", "name": "x", "mods": [
            {"name": "Renamed", "remote_id": 77}, {"name": "A"}, {"name": "Ghost", "remote_id": "999"}, {"name": "B", "enabled": False}]}
        nid, missing = self.s.import_shared(doc, self.mods, "ck3")
        self.assertEqual((self.s.get(nid)["mods"], self.s.get(nid)["disabled"], missing),
                         (["ws:77", "local:A", "local:B"], ["local:B"], ["Ghost"]))

    def test_a_playset_for_another_game_is_refused_with_a_clear_message(self):
        doc = {"format": "modmanager-playset", "game": "eu5", "name": "x", "mods": []}
        with self.assertRaises(ValueError) as e:
            self.s.import_shared(doc, self.mods, "ck3")
        self.assertIn("eu5", str(e.exception))
        self.assertEqual(self.s.data["playsets"], {})

    def test_files_from_the_standalone_managers_are_accepted(self):
        old_vic = {"format": "vic3mm-playset", "version": 1, "name": "old", "notes": "n", "launch_args": [],
                   "auto_sort": True, "mods": [{"name": "A", "remote_id": None, "enabled": True}]}
        nid, _ = self.s.import_shared(old_vic, self.mods, "vic3")
        self.assertEqual(self.s.get(nid)["mods"], ["local:A"])
        old_eu = {"format": "eu5mm-playset/1", "name": "e", "notes": "", "mods": [{"id": "local:B", "name": "B", "remote_id": None, "enabled": True}]}
        nid, _ = self.s.import_shared(old_eu, self.mods, "eu5")
        self.assertEqual(self.s.get(nid)["mods"], ["local:B"])
        with self.assertRaises(ValueError):  # a vic3 file in the EU5 view
            self.s.import_shared(old_vic, self.mods, "eu5")

    def test_hostile_documents_are_rejected_and_create_nothing(self):
        bad = [None, [], "x", {"format": "other"}, {"format": "modmanager-playset", "mods": "x"},
               {"format": "modmanager-playset", "mods": [1]}, {"format": "modmanager-playset", "mods": [{"name": 5}]},
               {"format": "modmanager-playset", "mods": [{"remote_id": ["x"]}]},
               {"format": "modmanager-playset", "mods": [{"enabled": "yes"}]},
               {"format": "modmanager-playset", "mods": [{}] * 6000},
               {"format": "modmanager-playset", "name": "x" * 500, "mods": []},
               {"format": "modmanager-playset", "mods": [], "launch_args": ["; rm -rf /"]},
               {"format": "modmanager-playset", "mods": [], "notes": "n" * 5000}]
        for doc in bad:
            with self.assertRaises(ValueError, msg=str(doc)[:60]):
                self.s.import_shared(doc, self.mods, "ck3")
        self.assertEqual(self.s.data["playsets"], {})


class MovingFromStandaloneManagers(Base):
    def legacy(self, name, doc):
        d = self.r / "xdg" / name
        d.mkdir(parents=True)
        (d / "playsets.json").write_text(json.dumps(doc))

    def test_first_start_adopts_old_playsets_without_touching_them(self):
        self.legacy("ck3mm", {"active": "p1", "playsets": {
            "p1": {"id": "p1", "name": "Old CK3 set", "mods": ["local:A", "ws:5"], "disabled": ["ws:5"], "created": 1}}, "settings": {}})
        before = (self.r / "xdg/ck3mm/playsets.json").read_text()
        s = Store(game=games.CK3)
        ps = s.get("p1")
        self.assertEqual((ps["name"], ps["mods"], ps["disabled"]), ("Old CK3 set", ["local:A", "ws:5"], ["ws:5"]))
        self.assertEqual((ps["notes"], ps["auto_sort"], ps["launch_args"]), ("", True, []))  # defaults filled in
        self.assertEqual(s.data["active"], "p1")
        self.assertEqual((self.r / "xdg/ck3mm/playsets.json").read_text(), before)
        self.assertTrue((self.r / "cfg/ck3/playsets.json").is_file())

    def test_each_game_only_adopts_its_own_old_file(self):
        self.legacy("ck3mm", {"playsets": {"p": {"id": "p", "name": "ck3 one", "mods": []}}})
        self.assertEqual(Store(game=games.EU5).data["playsets"], {})
        self.assertEqual(list(Store(game=games.CK3).data["playsets"]), ["p"])

    def test_old_eu5_file_with_settings_keeps_working(self):
        self.legacy("eu5mm", {"active": "e1", "playsets": {"e1": {"id": "e1", "name": "EU", "mods": ["local:X"], "disabled": [], "notes": "keep"}},
                              "settings": {"game_dir": "/old/path", "setup_done": True}})
        s = Store(game=games.EU5)
        self.assertEqual(s.get("e1")["notes"], "keep")

    def test_only_on_first_start_never_overwrites_current_data(self):
        self.legacy("vic3mm", {"playsets": {"o": {"id": "o", "name": "old", "mods": []}}})
        s = Store(game=games.VIC3)
        s.create("mine")
        s.delete("o")
        again = Store(game=games.VIC3)
        self.assertEqual([p["name"] for p in again.data["playsets"].values()], ["mine"])

    def test_junk_legacy_files_are_ignored(self):
        for junk in ("{bad", "[]", '{"playsets": []}', '{"playsets": {"x": 5}}'):
            d = self.r / "xdg/ck3mm"
            d.mkdir(parents=True, exist_ok=True)
            (d / "playsets.json").write_text(junk)
            for f in (self.r / "cfg/ck3/playsets.json",):
                f.unlink() if f.exists() else None
            self.assertEqual(Store(game=games.CK3).data["playsets"], {}, junk)

    def test_gameapp_reports_where_playsets_came_from(self):
        self.legacy("vic3mm", {"playsets": {"o": {"id": "o", "name": "old", "mods": []}}})
        (self.r / "u/mod").mkdir(parents=True)
        app = GameApp(games.VIC3, user_dir=self.r / "u", workshop_dir=self.r / "none", autodetect=False)
        self.assertIn("vic3mm", app.state()["imported_from"])
        self.assertEqual([p["name"] for p in app.state()["playsets"]], ["old"])


if __name__ == "__main__":
    unittest.main()
