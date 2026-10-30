"""The per-game log: what the app found, what Play handed to the game, what the game's files said before and after."""
import json
import os
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

from modmanager import games, gamelog
from modmanager.server import GameApp
from modmanager.library import Library
from modmanager.store import Store
from tests.helpers import mkmod


class GameLog(unittest.TestCase):
    def setUp(self):
        t = tempfile.TemporaryDirectory()
        self.addCleanup(t.cleanup)
        self.r = Path(t.name)
        p = mock.patch.dict(os.environ, {"MODMANAGER_LOG_DIR": str(self.r / "log"), "MODMANAGER_CONFIG_DIR": str(self.r / "cfg")})
        p.start()
        self.addCleanup(p.stop)
        self.user = self.r / "user"
        mkmod(self.user, "A")
        mkmod(self.user, "B")
        (self.user / "playsets.json").write_text(json.dumps({"playsets": [
            {"name": "Old", "isActive": True, "orderedListMods": [{"path": "C:/x/3450310/1/", "isEnabled": True}]}]}))
        self.app = GameApp(games.EU5, user_dir=self.user, workshop_dir=self.r / "ws", game_exe=str(self.r / "eu5.exe"),
                           store=Store(self.r / "p.json"), library=Library(self.r / "l.json"), autodetect=False)
        (self.r / "eu5.exe").write_text("")

    def text(self):
        return gamelog.log_path("eu5").read_text(encoding="utf-8")

    def test_each_game_has_its_own_file_next_to_the_error_log(self):
        self.assertEqual(gamelog.log_path("eu5").name, "RoninModManager-eu5.log")
        self.assertNotEqual(gamelog.log_path("eu5"), gamelog.log_path("ck3"))

    def test_opening_a_game_says_what_was_found(self):
        t = self.text()
        self.assertIn("Europa Universalis V opened in the app", t)
        self.assertIn("2 local", t)
        self.assertIn("'Old': 1/1 mods enabled  [isActive]", t)

    def test_play_logs_the_mods_the_files_written_and_the_result(self):
        pid = self.app.store.create("Mine", ["local:A", "local:B"])
        with mock.patch("modmanager.launch.start", return_value={"via": "exe"}), mock.patch.dict(os.environ, {"MODMANAGER_FOLLOW_UP": "0"}):
            self.app.launch(pid)
        t = self.text()
        self.assertIn("PLAY: playset 'Mine'", t)
        self.assertIn("1. local:A  'A'", t)
        self.assertIn("before writing, the game's files say", t)
        self.assertIn("'Mine' made the active one", t)
        self.assertIn("active playset 'Mine', in order:", t)
        self.assertIn("started the game: {'via': 'exe'}", t)

    def test_a_failed_play_is_logged_with_the_reason(self):
        pid = self.app.store.create("Mine", ["local:A"])
        with mock.patch("modmanager.launch.start", side_effect=ValueError("no exe")), mock.patch.dict(os.environ, {"MODMANAGER_FOLLOW_UP": "0"}):
            with self.assertRaises(ValueError):
                self.app.launch(pid)
        self.assertIn("PLAY FAILED: ValueError: no exe", self.text())

    def test_the_follow_up_shows_when_the_game_put_its_own_playset_back(self):
        pid = self.app.store.create("Mine", ["local:A"])
        with mock.patch("modmanager.launch.start", return_value={"via": "exe"}), mock.patch.dict(os.environ, {"MODMANAGER_FOLLOW_UP": "0"}):
            self.app.launch(pid)
        (self.user / "playsets.json").write_text(json.dumps({"playsets": [
            {"name": "Old", "isActive": True, "orderedListMods": []}, {"name": "Mine", "orderedListMods": []}]}))
        with mock.patch.dict(os.environ, {"MODMANAGER_FOLLOW_UP": "1"}):
            gamelog.follow_up(games.EU5, self.user, delays=(0.05,))
        time.sleep(0.4)
        t = self.text()
        self.assertIn("0.05 s after Play: the game's files now say", t)
        after = t.split("0.05 s after Play")[1]
        self.assertIn("active playset 'Old'", after)
        self.assertIn("playsets.json as it is on disk", after)   # the file itself, to see what the game wrote
        self.assertIn('"name": "Old"', after)
        self.assertIn("changed in the last 15 min in the user folder:", after)
        self.assertIn("playsets.json", after.split("changed in the last 15 min")[1])

    def test_recent_files_look_one_folder_down_and_skip_mods(self):
        (self.user / "settings").mkdir()
        (self.user / "settings" / "last.json").write_text("{}")
        old = self.user / "old.txt"
        old.write_text("x")
        os.utime(old, (time.time() - 7200, time.time() - 7200))
        lines = "\n".join(gamelog.recent_files(self.user))
        self.assertIn("settings/last.json", lines)
        self.assertNotIn("old.txt", lines)
        self.assertNotIn("mod/", lines)

    def test_the_windows_user_name_is_not_written(self):
        with mock.patch.dict(os.environ, {"USERNAME": "Somebody"}):
            gamelog.log("eu5", r"C:\Users\Somebody\Documents\x and c:/users/somebody/y")
        t = self.text()
        self.assertNotIn("omebody", t)
        self.assertIn("<user>", t)

    def test_a_big_log_is_rotated_and_a_bad_folder_never_raises(self):
        gamelog.log_path("eu5").write_text("x" * (gamelog.MAX_BYTES + 10))
        gamelog.log("eu5", "fresh")
        self.assertTrue(gamelog.log_path("eu5").with_name("RoninModManager-eu5.log.1").is_file())
        self.assertIn("fresh", self.text())
        blocker = self.r / "blocker"
        blocker.write_text("")
        with mock.patch.dict(os.environ, {"MODMANAGER_LOG_DIR": str(blocker / "sub")}):
            gamelog.log("eu5", "nowhere to write")

    def test_unreadable_game_files_are_described_not_raised(self):
        (self.user / "playsets.json").write_text("{nope")
        self.assertIn("could not be read as JSON", "\n".join(gamelog.snapshot(games.EU5, self.user)))
        self.assertIn("not there", "\n".join(gamelog.snapshot(games.EU5, self.r / "nowhere")))


if __name__ == "__main__":
    unittest.main()
