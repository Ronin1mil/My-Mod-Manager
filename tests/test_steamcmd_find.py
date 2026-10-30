"""A Rescan looks for steamcmd when Settings has none, and fills in the path (and the one cached account name)."""
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from modmanager import games, workshop
from modmanager.library import Library
from modmanager.server import GameApp
from modmanager.store import Store
from tests import REAL_FIND_STEAMCMD

VDF = '''"InstallConfigStore"
{
	"Software" { "Valve" { "Steam" {
		"Accounts"
		{
			"%s"
			{
				"SteamID"		"76561190000000000"
			}
		}
		"ConnectCache" { "abc" "def" }
	} } }
}
'''


class _Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.r = Path(self.tmp.name)

    def steamcmd(self, folder, accounts=("some_user",)):
        d = self.r / folder
        (d / "config").mkdir(parents=True)
        exe = d / ("steamcmd.exe" if os.name == "nt" else "steamcmd.sh")
        exe.write_text("")
        if accounts is not None:
            names = "".join(f'"{a}" {{ "SteamID" "1" }}\n' for a in accounts)
            (d / "config" / "config.vdf").write_text(VDF.replace('"%s"\n\t\t\t{\n\t\t\t\t"SteamID"\t\t"76561190000000000"\n\t\t\t}', names))
        return exe


class Find(_Base):
    def test_first_existing_candidate_wins_and_nothing_is_run(self):
        exe = self.steamcmd("b")
        with mock.patch.object(workshop, "steamcmd_candidates", return_value=[self.r / "a" / exe.name, exe]), \
                mock.patch("subprocess.Popen", side_effect=AssertionError("ran something")):
            self.assertEqual(REAL_FIND_STEAMCMD(), exe)
        with mock.patch.object(workshop, "steamcmd_candidates", return_value=[self.r / "nope.exe"]):
            self.assertIsNone(REAL_FIND_STEAMCMD())

    def test_usual_places_include_valves_suggested_folder_and_downloads(self):
        places = [str(p).replace("\\", "/").lower() for p in workshop.steamcmd_candidates()]
        if os.name == "nt":
            self.assertTrue(any(p.endswith(":/steamcmd/steamcmd.exe") for p in places))
            self.assertTrue(any(p.endswith("/downloads/steamcmd.exe") for p in places))
        else:
            self.assertTrue(any(p.endswith("/steamcmd/steamcmd.sh") for p in places))

    def test_account_names_come_only_from_the_accounts_block(self):
        self.assertEqual(workshop.steamcmd_accounts(self.steamcmd("one")), ["some_user"])
        self.assertEqual(workshop.steamcmd_accounts(self.steamcmd("two", ("a_1", "b_2"))), ["a_1", "b_2"])
        self.assertEqual(workshop.steamcmd_accounts(self.steamcmd("none", None)), [])


class OnRescan(_Base):
    def app(self, **settings):
        a = GameApp(games.VIC3, user_dir=self.r / "user", workshop_dir=self.r / "ws", store=Store(self.r / "p.json"),
                    library=Library(self.r / "l.json"), autodetect=False)
        if settings:
            a.store.update_settings(**settings)
        return a

    def test_empty_settings_get_the_path_and_the_one_account(self):
        exe = self.steamcmd("sc")
        a = self.app()
        self.assertEqual(a.look_for_steamcmd(find=lambda: exe), {"steamcmd": str(exe), "steam_user": "some_user"})
        s = a.store.settings()
        self.assertEqual((s["steamcmd"], s["steam_user"]), (str(exe), "some_user"))

    def test_a_working_setting_is_never_replaced(self):
        mine, other = self.steamcmd("mine"), self.steamcmd("other")
        a = self.app(steamcmd=str(mine))
        self.assertIsNone(a.look_for_steamcmd(find=lambda: other))
        self.assertEqual(a.store.settings()["steamcmd"], str(mine))

    def test_a_setting_whose_file_is_gone_is_replaced_but_the_account_name_kept(self):
        exe = self.steamcmd("sc")
        a = self.app(steamcmd=str(self.r / "moved" / "steamcmd.exe"), steam_user="kept_name")
        self.assertEqual(a.look_for_steamcmd(find=lambda: exe), {"steamcmd": str(exe), "steam_user": ""})
        self.assertEqual(a.store.settings()["steam_user"], "kept_name")

    def test_two_cached_accounts_leave_the_name_for_the_user(self):
        exe = self.steamcmd("sc", ("a_1", "b_2"))
        a = self.app()
        self.assertEqual(a.look_for_steamcmd(find=lambda: exe)["steam_user"], "")

    def test_nothing_found_changes_nothing(self):
        a = self.app()
        self.assertIsNone(a.look_for_steamcmd(find=lambda: None))
        self.assertEqual(a.store.settings()["steamcmd"], "")


if __name__ == "__main__":
    unittest.main()
