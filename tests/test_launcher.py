"""Importing the playsets that already exist in the game's own launcher (launcher-v2.sqlite)."""
import hashlib
import os
import sqlite3
import tempfile
import unittest
from pathlib import Path

from modmanager import games, launcherdb
from tests.helpers import GameCase, mkmod, mkworkshop

def build(path, playsets, mods, links, with_removed=True, position_as_text=False):
    con = sqlite3.connect(path)
    pcols = "id TEXT PRIMARY KEY, name TEXT, isActive INTEGER" + (", isRemoved INTEGER" if with_removed else "")
    con.execute(f"CREATE TABLE playsets ({pcols})")
    con.execute(f"CREATE TABLE playsets_mods (playsetId TEXT, modId TEXT, enabled INTEGER, position {'TEXT' if position_as_text else 'INTEGER'})")
    con.execute("CREATE TABLE mods (id TEXT PRIMARY KEY, displayName TEXT, steamId TEXT, pdxId TEXT, gameRegistryId TEXT, dirPath TEXT, source TEXT)")
    for p in playsets:
        if with_removed:
            con.execute("INSERT INTO playsets VALUES (?,?,?,?)", (p["id"], p["name"], int(p.get("active", 0)), int(p.get("removed", 0))))
        else:
            con.execute("INSERT INTO playsets VALUES (?,?,?)", (p["id"], p["name"], int(p.get("active", 0))))
    for m in mods:
        con.execute("INSERT INTO mods VALUES (?,?,?,?,?,?,?)", (m["id"], m["name"], m.get("steam", ""), m.get("pdx", ""), m.get("reg", ""), m.get("dir", ""), m.get("source", "steam")))
    for pid, mid, en, pos in links:
        con.execute("INSERT INTO playsets_mods VALUES (?,?,?,?)", (pid, mid, en, str(pos) if position_as_text else pos))
    con.commit()
    con.close()


def digest(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


class Reading(unittest.TestCase):
    def setUp(self):
        t = tempfile.TemporaryDirectory()
        self.addCleanup(t.cleanup)
        self.r = Path(t.name)

    def test_playsets_come_back_in_launcher_order_without_removed_ones(self):
        db = self.r / "launcher-v2.sqlite"
        build(db, [{"id": "a", "name": "Main", "active": 1}, {"id": "b", "name": "Old", "removed": 1}, {"id": "c", "name": "Test"}],
              [{"id": "m1", "name": "One", "steam": "111"}, {"id": "m2", "name": "Two", "steam": "222"}, {"id": "m3", "name": "Three"}],
              [("a", "m2", 1, 1), ("a", "m1", 1, 0), ("a", "m3", 0, 2), ("c", "m1", 1, 0)])
        sets = launcherdb.read_playsets(db)
        self.assertEqual([s["name"] for s in sets], ["Main", "Test"])  # the removed one is gone
        main = sets[0]
        self.assertTrue(main["active"])
        self.assertEqual([m["name"] for m in main["mods"]], ["One", "Two", "Three"])  # by position
        self.assertEqual([m["enabled"] for m in main["mods"]], [True, True, False])

    def test_the_launchers_file_is_never_changed(self):
        db = self.r / "launcher-v2.sqlite"
        build(db, [{"id": "a", "name": "Main"}], [{"id": "m1", "name": "One"}], [("a", "m1", 1, 0)])
        before = digest(db)
        launcherdb.read_playsets(db)
        self.assertEqual(digest(db), before)
        self.assertEqual(os.listdir(self.r), ["launcher-v2.sqlite"])  # no stray files beside it either

    def test_older_layouts_and_text_positions_are_tolerated(self):
        db = self.r / "launcher-v2.sqlite"
        build(db, [{"id": "a", "name": "Main"}], [{"id": "m1", "name": "One"}, {"id": "m2", "name": "Two"}],
              [("a", "m2", 1, 10), ("a", "m1", 1, 9)], with_removed=False, position_as_text=True)
        sets = launcherdb.read_playsets(db)
        self.assertEqual([m["name"] for m in sets[0]["mods"]], ["One", "Two"])

    def test_a_damaged_file_gives_a_readable_error(self):
        db = self.r / "launcher-v2.sqlite"
        db.write_bytes(b"this is not a database at all" * 50)
        with self.assertRaises(ValueError) as cm:
            launcherdb.read_playsets(db)
        self.assertNotIn("Traceback", str(cm.exception))

    def test_db_files_finds_both_names_and_nothing_when_absent(self):
        self.assertEqual(launcherdb.db_files(self.r), [])
        self.assertEqual(launcherdb.db_files(None), [])
        (self.r / "launcher-v2_openbeta.sqlite").write_bytes(b"x")
        self.assertEqual([p.name for p in launcherdb.db_files(self.r)], ["launcher-v2_openbeta.sqlite"])


class Matching(unittest.TestCase):
    MODS = {"ws:111": {"name": "Alpha", "root": "/ws/111"}, "local:beta": {"name": "Beta Mod", "root": "/u/mod/beta"},
            "local:gamma": {"name": "Gamma", "root": "/u/mod/gamma_dir"}}

    def test_each_way_of_naming_a_mod(self):
        m = launcherdb.match_mod
        self.assertEqual(m({"steam_id": "111"}, self.MODS), "ws:111")
        self.assertEqual(m({"registry_id": "mod/ugc_111.mod"}, self.MODS), "ws:111")
        self.assertEqual(m({"registry_id": "mod/beta.mod"}, self.MODS), "local:beta")
        self.assertEqual(m({"dir_path": "/u/mod/gamma_dir"}, self.MODS), "local:gamma")
        self.assertEqual(m({"name": "Beta Mod"}, self.MODS), "local:beta")
        self.assertIsNone(m({"name": "Nope", "steam_id": "9"}, self.MODS))

    def test_an_uninstalled_workshop_mod_is_kept_and_a_pdx_only_mod_is_reported(self):
        ps = {"mods": [{"steam_id": "111", "enabled": True}, {"steam_id": "999", "enabled": False, "name": "Gone"},
                       {"pdx_id": "5", "name": "PDX only", "enabled": True}, {"steam_id": "111", "enabled": True}]}
        order, off, lost = launcherdb.convert(ps, self.MODS)
        self.assertEqual(order, ["ws:111", "ws:999"])  # de-duplicated, uninstalled kept as a placeholder
        self.assertEqual(off, ["ws:999"])
        self.assertEqual(lost, ["PDX only"])


class Importing(GameCase):
    GAME = games.CK3

    def kw(self, g):
        base = super().kw(g)
        if g is self.GAME:
            mkworkshop(self.ws(g), 111, "Alpha")
            mkworkshop(self.ws(g), 222, "Beta")
            mkmod(self.user(g), "local_one", "Local One")
            build(self.user(g) / "launcher-v2.sqlite",
                  [{"id": "p1", "name": "Main", "active": 1}, {"id": "p2", "name": "Experiments"}],
                  [{"id": "m1", "name": "Alpha", "steam": "111", "reg": "mod/ugc_111.mod"}, {"id": "m2", "name": "Beta", "steam": "222"},
                   {"id": "m3", "name": "Local One", "reg": "mod/local_one.mod", "source": "local"}, {"id": "m4", "name": "Not installed", "steam": "333"}],
                  [("p1", "m1", 1, 0), ("p1", "m2", 1, 1), ("p1", "m3", 0, 2), ("p2", "m4", 1, 0), ("p2", "m2", 1, 1)])
        return base

    def names(self):
        return {p["name"]: p for p in self.req("GET", "/api/state")[1]["playsets"]}

    def test_info_lists_the_launchers_playsets(self):
        st, info, _ = self.req("GET", "/api/launcher")
        self.assertEqual(st, 200)
        self.assertTrue(info["found"])
        self.assertEqual([(p["name"], p["mods"], p["imported"]) for p in info["playsets"]], [("Main", 3, False), ("Experiments", 2, False)])

    def test_import_all_creates_playsets_with_order_state_and_placeholders(self):
        st, res, _ = self.post("/api/launcher/import", {})
        self.assertEqual((st, [i["name"] for i in res["imported"]]), (200, ["Main", "Experiments"]))
        ps = self.names()
        self.assertEqual(ps["Main"]["mods"], ["ws:111", "ws:222", "local:local_one"])
        self.assertEqual(ps["Main"]["disabled"], ["local:local_one"])  # disabled in the launcher stays disabled
        self.assertEqual(ps["Experiments"]["mods"], ["ws:333", "ws:222"])  # not installed -> placeholder, still in the playset
        self.assertEqual([i["missing"] for i in res["imported"]], [0, 1])
        self.assertEqual(self.req("GET", "/api/state")[1]["active"], ps["Main"]["id"])  # the launcher's active one, as the app only had a blank playset... or none

    def test_pressing_again_adds_nothing_until_something_is_missing(self):
        self.post("/api/launcher/import", {})
        st, res, _ = self.post("/api/launcher/import", {})
        self.assertEqual((res["imported"], res["skipped"]), ([], 2))
        self.post(f"/api/playsets/{self.names()['Experiments']['id']}/delete")  # deleted here: pressing the button brings it back
        res = self.post("/api/launcher/import", {})[1]
        self.assertEqual([i["name"] for i in res["imported"]], ["Experiments"])
        self.assertEqual(len(self.names()), 2)

    def test_only_the_chosen_ones(self):
        res = self.post("/api/launcher/import", {"ids": ["p2"]})[1]
        self.assertEqual([i["name"] for i in res["imported"]], ["Experiments"])
        self.assertEqual(self.req("POST", "/api/launcher/import", {"ids": "p1"})[0], 400)
        self.assertEqual(self.req("POST", "/api/launcher/import", {"ids": [1]})[0], 400)

    def test_a_name_clash_does_not_overwrite(self):
        self.new_playset([], game=self.GAME)  # named "T"
        self.post(f"/api/playsets/{list(self.names().values())[0]['id']}/update", {"name": "Main"})
        self.post("/api/launcher/import", {"ids": ["p1"]})
        self.assertEqual(sorted(self.names()), ["Main", "Main (launcher)"])

    def test_the_automatic_import_runs_once_and_respects_deletions(self):
        app = self.hub.app(self.GAME.id)
        app.auto_import_launcher = True
        app.auto_import()
        self.assertEqual(sorted(self.names()), ["Experiments", "Main"])
        for p in list(self.names().values()):
            self.post(f"/api/playsets/{p['id']}/delete")
        app.auto_import()  # already offered once: a playset deleted on purpose does not come back by itself
        self.assertEqual(self.names(), {})
        self.assertEqual(len(self.post("/api/launcher/import", {})[1]["imported"]), 2)  # but the button still can

    def test_no_launcher_database_is_not_an_error(self):
        self.hub.app(self.GAME.id)
        os.unlink(self.user() / "launcher-v2.sqlite")
        info = self.req("GET", "/api/launcher")[1]
        self.assertFalse(info["found"])
        self.assertEqual(self.post("/api/launcher/import", {})[1]["imported"], [])

    def test_a_broken_database_is_reported_not_raised(self):
        self.hub.app(self.GAME.id)
        (self.user() / "launcher-v2.sqlite").write_bytes(b"garbage" * 100)
        info = self.req("GET", "/api/launcher")[1]
        self.assertTrue(info["found"])
        self.assertTrue(info["error"])
        self.assertEqual(self.post("/api/launcher/import", {})[0], 400)

    def test_the_two_settings_exist_and_default_on(self):
        s = self.req("GET", "/api/games")[1]["settings"]
        self.assertTrue(s["auto_import_launcher"] and s["show_import_button"])
        out = self.post("/api/settings", {"show_import_button": False})[1]
        self.assertFalse(out["show_import_button"])


if __name__ == "__main__":
    unittest.main()


class WithoutSqlite(unittest.TestCase):
    """A copy of the app whose sqlite3 cannot be loaded must still start; only reading the launcher fails, readably."""

    def test_read_playsets_reports_missing_sqlite(self):
        import sys
        from unittest import mock
        with mock.patch.dict(sys.modules, {"sqlite3": None}):
            with self.assertRaises(ValueError) as cm:
                launcherdb.read_playsets("nonexistent.sqlite")
        self.assertIn("cannot read the launcher", str(cm.exception))

    def test_module_has_no_top_level_sqlite_import(self):
        import ast
        tree = ast.parse(Path(launcherdb.__file__).read_text(encoding="utf-8"))
        top = [n for n in tree.body if isinstance(n, (ast.Import, ast.ImportFrom))]
        self.assertFalse([n for n in top if any(a.name.split(".")[0] == "sqlite3" for a in getattr(n, "names", []))])
