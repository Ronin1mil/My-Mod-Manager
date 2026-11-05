"""Add to Steam: the app becomes a non-Steam game in shortcuts.vdf, read and written back exactly, only while Steam
is closed, with the old file backed up."""
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from modmanager import steamshortcut as ss
from tests import REAL_STEAM_ROOT


def game(name, exe, appid):
    return [("appid", appid), ("AppName", name), ("Exe", f'"{exe}"'), ("StartDir", '"C:\\games"'), ("icon", ""),
            ("ShortcutPath", ""), ("LaunchOptions", "--fast"), ("IsHidden", 0), ("LastPlayTime", 1700000000),
            ("tags", [("0", "favorite")])]


class Format(unittest.TestCase):
    def test_round_trip_is_byte_for_byte(self):
        root = [("shortcuts", [("0", game("Some Game", r"C:\g.exe", -123456)), ("1", game("Ünïcode ：name", r"D:\h.exe", -5))])]
        data = ss.dumps(root)
        self.assertEqual(ss.parse(data), root)
        self.assertEqual(ss.dumps(ss.parse(data)), data)

    def test_broken_files_are_refused(self):
        good = ss.dumps([("shortcuts", [("0", game("A", "a", -1))])])
        for bad in (good[:-6], good[:10] + b"\x07" + good[11:]):
            with self.assertRaises(ValueError):
                ss.parse(bad)


class Add(unittest.TestCase):
    def setUp(self):
        self.t = tempfile.TemporaryDirectory()
        self.addCleanup(self.t.cleanup)
        self.r = Path(self.t.name)
        self.vdf = self.r / "config" / "shortcuts.vdf"
        self.vdf.parent.mkdir()
        self.theirs = [("0", game("Their Game", "C:\their.exe", -77)), ("1", game("Another", "C:\b.exe", -78))]
        self.vdf.write_bytes(ss.dumps([("shortcuts", list(self.theirs))]))

    def add(self, **kw):
        return ss.add(self.r / "cfg", vdf=self.vdf, running=lambda: False, **kw)

    def entries(self):
        return ss.parse(self.vdf.read_bytes())[0][1]

    def test_added_after_the_others_which_are_kept_exactly(self):
        r = self.add()
        e = self.entries()
        self.assertEqual(e[:2], self.theirs)
        key, mine = e[2]
        mine = dict(mine)
        self.assertEqual((key, mine["AppName"], r["updated"]), ("2", "Ronin Mod Manager", False))
        self.assertTrue(mine["Exe"].startswith('"') and mine["StartDir"].startswith('"'))
        self.assertTrue(mine["appid"] < 0, "stored as a signed 32-bit number, like Steam's")
        self.assertEqual(Path(r["backup"]).read_bytes(), ss.dumps([("shortcuts", self.theirs)]))

    def test_a_second_add_updates_ours_and_keeps_what_steam_set_on_it(self):
        self.add()
        e = self.entries()
        k, mine = e[2]
        mine = [(f, 1234 if f == "LastPlayTime" else v) for f, v in mine]
        e[2] = (k, mine)
        self.vdf.write_bytes(ss.dumps([("shortcuts", e)]))
        r = self.add()
        e = self.entries()
        self.assertEqual((len(e), r["updated"], dict(e[2][1])["LastPlayTime"]), (3, True, 1234))

    def test_never_while_steam_runs(self):
        before = self.vdf.read_bytes()
        with self.assertRaisesRegex(ValueError, "Close Steam first"):
            ss.add(self.r / "cfg", vdf=self.vdf, running=lambda: True)
        self.assertEqual(self.vdf.read_bytes(), before)
        self.assertEqual(list(self.vdf.parent.glob("*backup*")), [])

    def test_no_file_yet_makes_one(self):
        self.vdf.unlink()
        r = self.add()
        self.assertEqual([dict(g)["AppName"] for _, g in self.entries()], ["Ronin Mod Manager"])
        self.assertEqual(r["backup"], "")

    def test_an_id_that_is_taken_is_not_reused(self):
        self.add()
        mine = dict(self.entries()[2][1])["appid"]
        self.vdf.write_bytes(ss.dumps([("shortcuts", self.theirs + [("2", game("Clash", "c", mine))])]))
        self.add()
        ids = [dict(g)["appid"] for _, g in self.entries()]
        self.assertEqual(len(ids), len(set(ids)))


class WhichAccount(unittest.TestCase):
    def setUp(self):
        self.t = tempfile.TemporaryDirectory()
        self.addCleanup(self.t.cleanup)
        self.root = Path(self.t.name)
        for acc in ("432796907", "1592241347"):
            (self.root / "userdata" / acc / "config").mkdir(parents=True)
        (self.root / "config").mkdir()

    def users(self, text):
        (self.root / "config" / "loginusers.vdf").write_text('"users"\n{\n' + text + "\n}\n", encoding="utf-8")

    def test_auto_login_account_then_the_latest_login(self):
        self.users('"76561198393062635"\n{\n"AutoLogin" "1"\n"timestamp" "100"\n}\n"76561199552507075"\n{\n"AutoLogin" "0"\n"timestamp" "999"\n}')
        self.assertEqual(ss.shortcuts_file(self.root).parent.parent.name, "432796907")
        self.users('"76561198393062635"\n{\n"timestamp" "100"\n}\n"76561199552507075"\n{\n"timestamp" "999"\n}')
        self.assertEqual(ss.shortcuts_file(self.root).parent.parent.name, "1592241347")

    def test_no_way_to_tell_is_an_error_not_a_guess(self):
        with self.assertRaisesRegex(ValueError, "which Steam account"):
            ss.shortcuts_file(self.root)

    def test_tests_never_see_the_real_steam(self):
        self.assertIsNone(ss.steam_root())
        self.assertFalse(ss.status()["available"])
        self.assertTrue(callable(REAL_STEAM_ROOT))


if __name__ == "__main__":
    unittest.main()
