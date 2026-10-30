import os
import sys
import tempfile
import unittest
from pathlib import Path

from modmanager import games, saves, updates
from modmanager.library import Library
from modmanager.server import GameApp, SaveVersionWarning
from modmanager.store import Store
from tests.test_core import mk

ACF = '''"AppWorkshop"
{
\t"appid"\t\t"1158310"
\t"WorkshopItemsInstalled"
\t{
\t\t"100"
\t\t{
\t\t\t"size"\t\t"5"
\t\t\t"timeupdated"\t\t"1000"
\t\t}
\t\t"200"
\t\t{
\t\t\t"timeupdated"\t\t"2000"
\t\t}
\t}
}
'''


def mkapp(r, version="1.15.1", **kw):
    return GameApp(games.CK3, user_dir=r / "user", workshop_dir=r / "ws", game_exe=str(r / "nope"), game_version_=version,
                   store=Store(r / "p.json"), library=Library(r / "l.json"), autodetect=False, **kw)


class Saves(unittest.TestCase):
    def test_minor_and_header(self):
        self.assertEqual(saves.minor_of("1.14.2.1"), "1.14")
        self.assertEqual(saves.minor_of(""), "")
        with tempfile.TemporaryDirectory() as r:
            f = Path(r) / "a.ck3"
            f.write_bytes(b'SAV0200\nmeta_data={\n\tversion="Fleur 1.14.2"\n\tname="x"\n}\n\x00\x01zip')
            self.assertEqual(saves.header_version(f), "1.14.2")
            f.write_bytes(b"\x00\x01\x02binary only")
            self.assertEqual(saves.header_version(f), "")

    @unittest.skipIf(sys.platform == "win32", "symlink test")
    def test_deactivate_only_undoes_our_link(self):
        with tempfile.TemporaryDirectory() as r:
            r = Path(r)
            game, mine, other = r / "u/save games", r / "cfg/saves/p1", r / "elsewhere"
            other.mkdir()
            saves.activate(game, mine)
            self.assertTrue(saves.deactivate(game, r / "cfg/saves").startswith("unlinked:"))
            self.assertTrue(game.is_dir() and not saves.is_link(game))
            self.assertEqual(saves.deactivate(game, r / "cfg/saves"), "unchanged")  # real folder untouched
            game.rmdir(); os.symlink(other, game)
            self.assertEqual(saves.deactivate(game, r / "cfg/saves"), "unchanged")  # someone else's link untouched

    def test_launch_warns_on_other_minor_release_and_can_be_acknowledged(self):
        with tempfile.TemporaryDirectory() as r:
            r = Path(r)
            mk(r / "user", "A", {"x.txt": ""}, meta={"name": "A"})
            app = mkapp(r, "1.15.1")
            pid = app.store.create("p", ["local:A"], separate_saves=False)
            saves.record_launch(app.cfg, "shared", "1.14.3")
            with self.assertRaises(SaveVersionWarning) as cm:
                app.launch(pid)
            self.assertEqual((cm.exception.info["saved_on"], cm.exception.info["game_version"]), ("1.14", "1.15"))
            self.assertIn("older", cm.exception.message)
            with self.assertRaises(ValueError):  # acknowledged: proceeds (and then stops at the missing exe)
                app.launch(pid, ack_version=True)
            saves.record_launch(app.cfg, "shared", "1.15.0")  # same minor release: patch changes are fine
            with self.assertRaises(ValueError):
                app.launch(pid)
            app.store.update_settings(save_version_check=False)
            saves.record_launch(app.cfg, "shared", "1.1.0")
            with self.assertRaises(ValueError):
                app.launch(pid)

    def test_newer_saves_message_and_header_wins_over_record(self):
        with tempfile.TemporaryDirectory() as r:
            r = Path(r)
            mk(r / "user", "A", {"x.txt": ""}, meta={"name": "A"})
            app = mkapp(r, "1.14.0")
            pid = app.store.create("p", ["local:A"], separate_saves=False)
            d = r / "user/save games"; d.mkdir(parents=True)
            (d / "s.ck3").write_bytes(b'meta{ version="1.16.0" }')
            saves.record_launch(app.cfg, "shared", "1.14.0")
            with self.assertRaises(SaveVersionWarning) as cm:
                app.launch(pid)
            self.assertEqual(cm.exception.info["source"], "save")
            self.assertIn("newer", cm.exception.message)


class Updates(unittest.TestCase):
    def test_vdf_and_local_times(self):
        with tempfile.TemporaryDirectory() as r:
            r = Path(r)
            (r / "steamapps/workshop/content/1158310").mkdir(parents=True)
            (r / "steamapps/workshop/appworkshop_1158310.acf").write_text(ACF)
            self.assertEqual(updates.local_times(r / "steamapps/workshop/content/1158310", "1158310"), {"100": 1000, "200": 2000})
            self.assertEqual(updates.local_times(r / "none", "1"), {})
            with self.assertRaises(ValueError):
                updates.parse_vdf('"a" { "b"')

    def test_check_statuses(self):
        mods = {"ws:100": {"id": "ws:100", "name": "Old", "source": "workshop", "remote_id": "100"},
                "ws:200": {"id": "ws:200", "name": "Fresh", "source": "workshop", "remote_id": "200"},
                "ws:300": {"id": "ws:300", "name": "Unknown", "source": "workshop", "remote_id": "300"},
                "local:x": {"id": "local:x", "name": "Local", "source": "local", "remote_id": None}}
        with tempfile.TemporaryDirectory() as r:
            r = Path(r)
            (r / "steamapps/workshop/content/1").mkdir(parents=True)
            (r / "steamapps/workshop/appworkshop_1.acf").write_text(ACF)
            post = lambda path, f: {"response": {"publishedfiledetails": [
                {"publishedfileid": "100", "result": 1, "time_updated": 1500},
                {"publishedfileid": "200", "result": 1, "time_updated": 2000},
                {"publishedfileid": "300", "result": 9}]}}
            res = updates.check(mods, r / "steamapps/workshop/content/1", "1", post)
            self.assertEqual([(x["name"], x["status"]) for x in res], [("Old", "update"), ("Unknown", "unknown"), ("Fresh", "current")])


class Trees(unittest.TestCase):
    def test_mod_and_result_tree(self):
        with tempfile.TemporaryDirectory() as r:
            r = Path(r)
            mk(r / "user", "A", {"common/a.txt": "", "common/shared.txt": ""}, meta={"name": "A"})
            mk(r / "user", "B", {"common/b.txt": "", "common/shared.txt": ""}, meta={"name": "B"})
            app = mkapp(r)
            app.rescan()
            pid = app.store.create("p", ["local:A", "local:B"])
            t = {f["path"]: f for f in app.mod_tree(pid, "local:A")["files"]}
            self.assertEqual(t["common/shared.txt"]["overridden_by"], "local:B")
            self.assertIsNone(t["common/a.txt"]["overridden_by"])
            res = app.result_tree(pid)
            by = {p: (res["mods"][w], c) for p, w, c in res["files"]}
            self.assertEqual(by["common/shared.txt"], ("local:B", 2))
            self.assertEqual(by["common/a.txt"], ("local:A", 1))
            with self.assertRaises(ValueError):
                app.mod_tree(pid, "local:ghost")
