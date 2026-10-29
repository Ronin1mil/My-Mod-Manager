import json
import os
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

from modmanager import launch, scan
from modmanager.library import Library
from modmanager import games
from modmanager.server import GameApp
from modmanager.store import Store

STUB = """#!{py}
import json, os, sys
d = os.path.dirname(os.path.abspath(__file__))
cl = os.path.join(os.environ["STUB_USER_DIR"], os.environ["STUB_LOAD_FILE"])
json.dump({{"args": sys.argv[1:], "cwd": os.getcwd(), "content_load": json.load(open(cl))}},
          open(os.path.join(d, "launch-record.json"), "w"))
"""


class T(unittest.TestCase):
    def test_validate_args(self):
        self.assertEqual(launch.validate_launch_args([" -debug_mode ", "", "-a=b:c"]), ["-debug_mode", "-a=b:c"])
        for bad in (["debug"], ["-a b"], ["-x;rm"], ["-$(id)"], ["-"], ["-applaunch"], ["-exec=foo"],
                    ["-a"] * 9, [1], "nope", ["-" + "a" * 70]):
            with self.assertRaises(ValueError, msg=bad):
                launch.validate_launch_args(bad)

    def test_steam_url(self):
        self.assertEqual(launch.steam_url(games.VIC3, []), "steam://run/529340")
        self.assertEqual(launch.steam_url(games.VIC3, ["-debug_mode", "-a=b"]), "steam://run/529340//-debug_mode%20-a=b/")

    @unittest.skipIf(sys.platform == "win32", "stub is a shebang script")
    def test_play_runs_game_with_exact_args_and_profile_mods_for_every_game(self):
        for g in games.GAMES.values():
            with self.subTest(game=g.id), tempfile.TemporaryDirectory() as r:
                r = Path(r)
                with mock.patch.dict(os.environ, {"MODMANAGER_CONFIG_DIR": str(r / "cfg"), "STUB_USER_DIR": str(r / "user"),
                                                  "STUB_LOAD_FILE": g.load_file}):
                    for n in ("A", "B"):
                        d = r / "user/mod" / n
                        (d / ".metadata").mkdir(parents=True)
                        (d / ".metadata/metadata.json").write_text(json.dumps({"name": n}))
                        (r / f"user/mod/{n}.mod").write_text(f'name="{n}"\npath="mod/{n}"\n')
                    exe = r / "game/start.sh"
                    exe.parent.mkdir()
                    exe.write_text(STUB.format(py=sys.executable))
                    exe.chmod(0o755)
                    app = GameApp(g, user_dir=r / "user", workshop_dir=r / "none", game_exe=str(exe), game_version_="1.7.6",
                                  store=Store(r / "p.json"), library=Library(r / "l.json"), autodetect=False)
                    pid = app.store.create("p", ["local:B", "local:A"], separate_saves=True, launch_args=["-debug_mode"])
                    app.update(pid, {"disabled": ["local:A"]})
                    res = app.launch(pid)
                    self.assertEqual((res["via"], res["written"], res["saves"], res["file"]), ("exe", 1, "linked", g.load_file))
                    rec = r / "game/launch-record.json"
                    for _ in range(100):
                        if rec.is_file() and rec.stat().st_size:
                            break
                        time.sleep(0.05)
                    got = json.loads(rec.read_text())
                    self.assertEqual(got["args"], ["-debug_mode"])
                    self.assertEqual(Path(got["cwd"]).resolve(), exe.parent.resolve())
                    want = ["mod/B.mod"] if g.load_style == "descriptor" else ["mod/B"]
                    self.assertEqual(got["content_load"]["enabled_mods"], want)
                    self.assertTrue(os.path.islink(r / "user/save games"))
                    self.assertTrue(str(r / "cfg" / g.id / "saves") in os.readlink(r / "user/save games"))  # per game

    def test_missing_exe_is_a_clear_error(self):
        with self.assertRaises(ValueError):
            launch.start(games.VIC3, "/nope/game", [])


if __name__ == "__main__":
    unittest.main()
