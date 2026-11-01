"""CK3: every change to the active playset goes into dlc_load.json and the Paradox launcher's own playset, so a game
started from Steam (through the launcher) has it too. Built on a small launcher database with the real columns."""
import json
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from modmanager import games, launchersync

SCHEMA = """
CREATE TABLE playsets (id char(36) PRIMARY KEY NOT NULL, name varchar(255) NOT NULL, isActive boolean, loadOrder varchar(255),
  pdxId INT, pdxUserId char(36), createdOn datetime NOT NULL, updatedOn datetime, syncedOn datetime, isRemoved boolean NOT NULL,
  hasNotApprovedChanges boolean NOT NULL, syncState varchar(255), state TEXT NOT NULL, owned boolean NOT NULL,
  author varchar(255) NOT NULL, subscribersCount INTEGER NOT NULL, ratingsCount INTEGER NOT NULL, offDisk boolean NOT NULL,
  lastUsedAt datetime);
CREATE TABLE playsets_mods (playsetId char(36) NOT NULL, modId char(36) NOT NULL, enabled boolean, position INTEGER);
CREATE TABLE mods (id char(36) PRIMARY KEY NOT NULL, steamId varchar(255), gameRegistryId TEXT, displayName varchar(255),
  dirPath TEXT, status TEXT NOT NULL, source TEXT NOT NULL);
"""


def make_db(user, extra_mods=()):
    user.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(str(user / "launcher-v2.sqlite"))
    con.executescript(SCHEMA)
    rows = [("m-cheat", "2986538297", "mod/ugc_2986538297.mod", "Cheat Menu", "W:\\ws\\2986538297"),
            ("m-ss", None, "mod/swords_sorcery.mod", "Swords & Sorcery", "G:\\mods\\swords_sorcery"),
            ("m-big", "111", "mod/ugc_111.mod", "Big Mod", "W:\\ws\\111"), *extra_mods]
    for mid, steam, reg, name, path in rows:
        con.execute("INSERT INTO mods VALUES (?, ?, ?, ?, ?, 'ready_to_play', ?)", (mid, steam, reg, name, path, "steam" if steam else "local"))
    for pid, name, active in (("p-ss", "Swords & Sorcery", 0), ("p-other", "Africa", 1)):
        con.execute("INSERT INTO playsets (id, name, isActive, createdOn, isRemoved, hasNotApprovedChanges, state, owned, author,"
                    " subscribersCount, ratingsCount, offDisk) VALUES (?, ?, ?, 1, 0, 0, 'private', 1, '', 0, 0, 0)", (pid, name, active))
    con.executemany("INSERT INTO playsets_mods VALUES (?, ?, 1, ?)", [("p-ss", "m-ss", 0), ("p-other", "m-big", 0)])
    con.commit()
    con.close()


MODS = {"ws:2986538297": {"id": "ws:2986538297", "name": "Cheat Menu", "root": "W:\\ws\\2986538297", "remote_id": "2986538297", "source": "workshop"},
        "local:swords_sorcery": {"id": "local:swords_sorcery", "name": "Swords & Sorcery", "root": "G:\\mods\\swords_sorcery", "remote_id": None, "source": "local"},
        "local:new": {"id": "local:new", "name": "Brand New", "root": "G:\\mods\\new", "remote_id": None, "source": "local"}}
REG = lambda m: f"mod/{m['id'].split(':', 1)[1]}.mod"


class Sync(unittest.TestCase):
    def setUp(self):
        self.t = tempfile.TemporaryDirectory()
        self.addCleanup(self.t.cleanup)
        self.user = Path(self.t.name) / "CK3"
        make_db(self.user)
        self.db = self.user / "launcher-v2.sqlite"

    def q(self, sql, *a):
        con = sqlite3.connect(str(self.db))
        try:
            return con.execute(sql, a).fetchall()
        finally:
            con.close()

    def sync(self, name="Swords & Sorcery", enabled=("ws:2986538297", "local:swords_sorcery"), disabled=(), running=False):
        return launchersync.sync(self.user, name, list(enabled), list(disabled), MODS, REG, running=lambda: running)

    def test_same_name_playset_gets_the_mods_in_load_order_and_becomes_active(self):
        r = self.sync()
        self.assertEqual((r["status"], r["created"], r["missing"]), ("synced", False, []))
        self.assertEqual(self.q("SELECT modId, enabled, position FROM playsets_mods WHERE playsetId='p-ss' ORDER BY position"),
                         [("m-cheat", 1, 0), ("m-ss", 1, 1)])
        self.assertEqual(self.q("SELECT name FROM playsets WHERE isActive=1"), [("Swords & Sorcery",)])
        self.assertEqual(self.q("SELECT modId FROM playsets_mods WHERE playsetId='p-other'"), [("m-big",)], "other playsets untouched")
        self.assertEqual(self.q("PRAGMA integrity_check"), [("ok",)])

    def test_switched_off_mods_stay_listed_but_off(self):
        self.sync(enabled=["local:swords_sorcery"], disabled=["ws:2986538297"])
        self.assertEqual(self.q("SELECT modId, enabled FROM playsets_mods WHERE playsetId='p-ss' ORDER BY position"),
                         [("m-ss", 1), ("m-cheat", 0)])

    def test_a_new_name_makes_a_new_launcher_playset(self):
        r = self.sync(name="Cheat test", enabled=["ws:2986538297"])
        self.assertTrue(r["created"])
        rows = self.q("SELECT id, isActive, isRemoved, state, owned FROM playsets WHERE name='Cheat test'")
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0][1:], (1, 0, "private", 1))
        self.assertEqual(self.q("SELECT modId FROM playsets_mods WHERE playsetId=?", rows[0][0]), [("m-cheat",)])

    def test_mods_the_launcher_does_not_know_are_reported_not_invented(self):
        r = self.sync(enabled=["local:swords_sorcery", "local:new"])
        self.assertEqual(r["missing"], ["Brand New"])
        self.assertEqual(self.q("SELECT count(*) FROM mods"), [(3,)])

    def test_never_while_the_launcher_runs(self):
        before = self.db.read_bytes()
        self.assertEqual(self.sync(running=True)["status"], "launcher_open")
        self.assertEqual(self.db.read_bytes(), before)
        self.assertEqual(list(self.user.glob("*ronin-backup*")), [])

    def test_backed_up_once_a_day_before_the_first_change(self):
        before = self.db.read_bytes()
        self.sync()
        self.sync(enabled=["local:swords_sorcery"])
        backups = list(self.user.glob("launcher-v2.sqlite.ronin-backup-*"))
        self.assertEqual(len(backups), 1)
        self.assertEqual(backups[0].read_bytes(), before)

    def test_no_launcher_database_is_not_an_error(self):
        self.db.unlink()
        self.assertEqual(self.sync()["status"], "no_db")


class AfterEveryChange(unittest.TestCase):
    """Through the HTTP API, like the page: a change to the active CK3 playset writes the game's files at once."""

    def server(self, game):
        from tests.test_server import Base
        b = type("B", (Base,), {"GAME": game, "runTest": lambda s: None})()
        b.setUp()
        self.addCleanup(b.tearDown)
        return b

    def test_an_edit_writes_dlc_load_and_the_launcher_playset(self):
        b = self.server(games.CK3)
        make_db(b.r / "user", [("m-c", None, "mod/c.mod", "C", str(b.r / "user" / "mod" / "c"))])
        pid = b.new_playset()
        with mock.patch.object(launchersync, "launcher_running", return_value=False):
            b.post(f"/api/playsets/{pid}/activate")
            b.post(f"/api/playsets/{pid}/update", {"mods": ["local:c"]})
        load = json.loads((b.r / "user" / "dlc_load.json").read_text())
        self.assertEqual(load["enabled_mods"], ["mod/c.mod"])
        an = b.req("GET", f"/api/analyse/{pid}?fast=1")[1]
        self.assertEqual((an["game_sync"]["status"], an["game_sync"]["playset"], an["game_sync"]["missing"]), ("synced", "T", []))
        con = sqlite3.connect(str(b.r / "user" / "launcher-v2.sqlite"))
        try:
            self.assertEqual(con.execute("SELECT name FROM playsets WHERE isActive=1").fetchall(), [("T",)])
        finally:
            con.close()

    def test_other_games_wait_for_play(self):
        v = self.server(games.VIC3)
        pid = v.new_playset()
        with mock.patch.object(launchersync, "sync", side_effect=AssertionError("synced")):
            v.post(f"/api/playsets/{pid}/activate")
            v.post(f"/api/playsets/{pid}/update", {"mods": ["local:c"]})
        self.assertIsNone(v.req("GET", f"/api/analyse/{pid}?fast=1")[1]["game_sync"])


if __name__ == "__main__":
    unittest.main()
