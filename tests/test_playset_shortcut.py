"""A playset's own desktop shortcut: `--game <id> --play <playset>` starts the game with it without opening the app."""
import json
import os
import subprocess
import sys
import unittest
from pathlib import Path
from unittest import mock

from modmanager import games, shortcut
from modmanager.server import find_playset, play_playset
from modmanager.store import Store
from tests.helpers import GameCase, mkmod


class Names(unittest.TestCase):
    def test_arguments_take_plain_ids_only(self):
        self.assertEqual(shortcut.play_args("ck3", "ab12cd34"), "--game ck3 --play ab12cd34")
        for g, p in (("ck3", "a b"), ("ck3", '"x'), ("CK3;", "ab"), ("ck3", "")):
            with self.assertRaises(ValueError):
                shortcut.play_args(g, p)

    def test_file_name_leaves_out_what_windows_does_not_allow(self):
        self.assertEqual(shortcut.playset_name("Crusader Kings III", 'Big: "AGOT" / test?'), "Crusader Kings III - Big AGOT test.lnk")
        self.assertTrue(shortcut.playset_name("Stellaris", "x" * 200).endswith(".lnk"))

    def test_find_by_id_or_name(self):
        import tempfile
        with tempfile.TemporaryDirectory() as t:
            s = Store(Path(t) / "p.json")
            a, b = s.create("Main"), s.create("Twin")
            s.create("twin")
            self.assertEqual((find_playset(s, a), find_playset(s, "MAIN")), (a, a))
            with self.assertRaises(ValueError) as e:
                find_playset(s, "twin")
            self.assertIn("more than one", str(e.exception))
            with self.assertRaises(ValueError) as e:
                find_playset(s, "nope")
            self.assertIn("'Main'", str(e.exception))
            self.assertIn(b, s.data["playsets"])


class Playing(GameCase):
    GAME = games.CK3

    def test_play_writes_the_load_file_starts_the_game_and_makes_it_the_active_playset(self):
        mkmod(self.user(), "a", "A")
        first = self.new_playset([])
        pid = self.new_playset(["local:a"])
        self.post(f"/api/playsets/{first}/activate")
        app = self.hub.app("ck3")
        exe = self.r / "game.exe"
        exe.write_bytes(b"")
        app.game_exe = str(exe)
        with self.assertRaises(ValueError):   # two playsets are called "T"
            play_playset("ck3", "T", hub=self.hub)
        with mock.patch("modmanager.launch.start", return_value={"via": "exe"}) as start:   # a real program is not started
            res = play_playset("ck3", pid, hub=self.hub)
        self.assertEqual(start.call_args[0][1], str(exe))
        self.assertEqual((res["written"], res["playset"]), (1, "T"))
        self.assertEqual(json.loads((self.user() / "dlc_load.json").read_text())["enabled_mods"], ["mod/a.mod"])
        self.assertEqual(app.store.data["active"], pid)
        self.assertEqual(self.hub.settings.get()["last_game"], "ck3")


class ShortcutRoute(GameCase):
    GAME = games.CK3

    def test_off_windows_the_answer_is_the_command_line(self):
        pid = self.new_playset([])
        with mock.patch.object(shortcut, "supported", return_value=False):
            st, r, _ = self.post(f"/api/playsets/{pid}/shortcut")
        self.assertEqual(st, 200, r)
        self.assertFalse(r["made"])
        self.assertTrue(r["command"].endswith(f"--game ck3 --play {pid}"))
        self.assertEqual(self.post("/api/playsets/nomods/shortcut")[0], 400)

    def test_on_windows_a_shortcut_is_written_to_the_desktop(self):
        pid = self.new_playset([])
        desk = self.r / "Desktop"
        seen = {}

        def fake_powershell(argv, env=None, **kw):
            seen.update(env)
            Path(env["RMM_LNK"]).write_text("lnk")
            return subprocess.CompletedProcess(argv, 0, "", "")
        with mock.patch.object(shortcut, "supported", return_value=True), mock.patch.dict(os.environ, {"MODMANAGER_DESKTOP_DIR": str(desk)}):
            r = self.hub.playset_shortcut(self.hub.app("ck3"), pid, run=fake_powershell)
        self.assertTrue(r["made"])
        self.assertEqual(Path(r["path"]), desk / "Crusader Kings III - T.lnk")
        self.assertTrue(seen["RMM_ARGS"].endswith(f"--game ck3 --play {pid}"))
        self.assertIn("with the playset T", seen["RMM_DESC"])


class CommandLine(unittest.TestCase):
    def test_play_needs_game_and_an_unknown_playset_fails_with_a_message(self):
        import tempfile
        with tempfile.TemporaryDirectory() as t:
            env = {**os.environ, "MODMANAGER_CONFIG_DIR": str(Path(t) / "cfg"), "MODMANAGER_LOG_DIR": str(Path(t) / "log"),
                   "MODMANAGER_FETCH_LOGOS": "0", "MODMANAGER_AUTO_IMPORT": "0", "MODMANAGER_NO_DIALOG": "1"}
            r = subprocess.run([sys.executable, "-m", "modmanager", "--play", "x"], capture_output=True, text=True, env=env, timeout=60)
            self.assertEqual(r.returncode, 2)
            self.assertIn("--play needs --game", r.stderr)
            (Path(t) / "user/mod").mkdir(parents=True)
            r = subprocess.run([sys.executable, "-m", "modmanager", "--game", "ck3", "--user-dir", str(Path(t) / "user"),
                                "--workshop-dir", str(Path(t) / "ws"), "--play", "Nope"], capture_output=True, text=True, env=env, timeout=60)
            self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
            self.assertIn("could not start the game: No playset 'Nope'", r.stdout)


if __name__ == "__main__":
    unittest.main()
