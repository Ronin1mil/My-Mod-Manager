"""What a look at real installs changed (docs/22-checked-on-a-real-pc.md): how Play starts CK3 and Victoria 3, and
where Europa Universalis V's version comes from."""
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from modmanager import games, launch
from modmanager.library import Library
from modmanager.paths import game_version, launcher_exe
from modmanager.server import GameApp
from modmanager.store import Store
from tests.helpers import mkinstall, mkmod

# launcher/launcher-settings.json as CK3 1.20 ships it (trimmed)
CK3_SETTINGS = {"gameId": "ck3", "version": "1.20.1.2 (Crozier)", "rawVersion": "1.20.1.2",
                "exePath": "../binaries/ck3.exe", "exeArgs": ["-gdpr-compliant"]}


class Base(unittest.TestCase):
    def setUp(self):
        t = tempfile.TemporaryDirectory()
        self.addCleanup(t.cleanup)
        self.r = Path(t.name)
        p = mock.patch.dict(os.environ, {"MODMANAGER_CONFIG_DIR": str(self.r / "cfg")})
        p.start()
        self.addCleanup(p.stop)

    def install(self, game, settings=None, exe="binaries/ck3.exe"):
        root = mkinstall(self.r / "lib", game)
        if settings is not None:
            (root / "launcher/launcher-settings.json").write_text(json.dumps(settings))
        if exe:
            (root / exe).parent.mkdir(parents=True, exist_ok=True)
            (root / exe).write_bytes(b"")
        return root


class LauncherExe(Base):
    def test_the_exe_and_arguments_the_paradox_launcher_would_use(self):
        root = self.install(games.CK3, CK3_SETTINGS)
        exe, args = launcher_exe(root)
        self.assertEqual((exe, args), ((root / "binaries/ck3.exe").resolve(), ["-gdpr-compliant"]))

    def test_nothing_when_missing_outside_the_install_or_not_a_file(self):
        root = self.install(games.CK3, CK3_SETTINGS, exe=None)
        self.assertEqual(launcher_exe(root), (None, []))              # exe not there
        for rel in ("../../outside.exe", "", 5, None):
            (root / "launcher/launcher-settings.json").write_text(json.dumps({**CK3_SETTINGS, "exePath": rel}))
            (self.r / "lib/steamapps/common/outside.exe").write_bytes(b"")
            self.assertEqual(launcher_exe(root), (None, []), rel)
        self.assertEqual(launcher_exe(None), (None, []))
        self.assertEqual(launcher_exe(self.r / "nowhere"), (None, []))

    def test_odd_launcher_arguments_are_dropped(self):
        root = self.install(games.CK3, {**CK3_SETTINGS, "exeArgs": ["-gdpr-compliant", "; del", 3, "-a b", "-debug_mode"]})
        self.assertEqual(launcher_exe(root)[1], ["-gdpr-compliant", "-debug_mode"])


class Play(Base):
    def app(self, game, root):
        user = self.r / "user"
        mkmod(user, "A")
        return GameApp(game, user_dir=user, workshop_dir=self.r / "ws", game_dir=str(root), autodetect=False,
                       store=Store(self.r / "p.json"), library=Library(self.r / "l.json"))

    def test_ck3_and_vic3_start_the_game_exe_not_the_launcher_and_keep_playset_arguments(self):
        for g in (games.CK3, games.VIC3):
            with self.subTest(game=g.id):
                root = self.install(g, CK3_SETTINGS)
                a = self.app(g, root)
                pid = a.store.create("T", ["local:A"])
                a.store.update(pid, launch_args=["-debug_mode"])
                with mock.patch.object(launch.subprocess, "Popen") as po, mock.patch.object(launch.webbrowser, "open") as op:
                    res = a.launch(pid, ack_version=True)
                op.assert_not_called()
                self.assertEqual(res["via"], "exe")
                self.assertEqual(po.call_args[0][0], [str((root / "binaries/ck3.exe").resolve()), "-gdpr-compliant", "-debug_mode"])
                self.assertIn("not through the Paradox launcher", a._play_via())
                # without this Victoria 3 hands itself back to Steam, which opens the launcher (no steam_appid.txt)
                env = po.call_args[1]["env"]
                self.assertEqual((env["SteamAppId"], env["SteamGameId"]), (g.app_id, g.app_id))
                self.assertEqual(env.get("PATH"), os.environ.get("PATH"))

    def test_a_game_without_launcher_settings_still_goes_through_steam(self):
        root = self.install(games.EU5, {"rawVersion": "1.0.0"}, exe=None)
        a = self.app(games.EU5, root)
        pid = a.store.create("T", ["local:A"])
        with mock.patch.object(launch.webbrowser, "open") as op:
            self.assertEqual(a.launch(pid, ack_version=True)["via"], "steam")
        op.assert_called_once_with("steam://run/3450310")

    def test_an_exe_set_by_the_user_wins(self):
        root = self.install(games.CK3, CK3_SETTINGS)
        mine = self.r / "mine.exe"
        mine.write_bytes(b"")
        a = self.app(games.CK3, root)
        a.game_exe = str(mine)
        pid = a.store.create("T", ["local:A"])
        with mock.patch.object(launch.subprocess, "Popen") as po:
            a.launch(pid, ack_version=True)
        self.assertEqual(po.call_args[0][0], [str(mine)])

    def test_no_steam_app_id_for_a_game_without_one(self):
        g = games.Game(id="x", name="X", app_id="0", user_dir_name="X", install_dir_name="X", install_marker=("a",),
                       load_file="dlc_load.json", load_style="path", def_dirs=())
        self.assertNotIn("SteamAppId", launch.steam_env(g))


class Eu5Version(Base):
    def test_from_the_games_debug_log_when_the_install_has_no_launcher_folder(self):
        root = self.r / "eu5"
        (root / "game/in_game").mkdir(parents=True)
        user = self.r / "user"
        (user / "logs").mkdir(parents=True)
        (user / "logs/debug.log").write_text(
            "[23:16:15][dlc_reloadable.cpp:390]: Mod X (x) version 1.4.* successfully matched game version 1.4.5.\n"
            "[23:16:15][dlc_reloadable.cpp:395]: Mod Y (y) version 1.3.* does not match game version 1.4.5.\n")
        self.assertEqual(game_version(root, games.EU5, user), "1.4.5")
        self.assertEqual(game_version(root, games.EU5), "")
        self.assertEqual(game_version(root, games.EU5, self.r / "no-user"), "")

    def test_launcher_settings_still_win(self):
        root = self.install(games.CK3, CK3_SETTINGS)
        user = self.r / "user"
        (user / "logs").mkdir(parents=True)
        (user / "logs/debug.log").write_text("matched game version 9.9.9")
        self.assertEqual(game_version(root, games.CK3, user), "1.20.1.2")


if __name__ == "__main__":
    unittest.main()
