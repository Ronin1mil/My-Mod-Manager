"""The desktop icon: asked about once at start-up, made by Windows itself, pointing at this copy of the app."""
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from modmanager import shortcut
from modmanager.server import Hub
from modmanager.store import GlobalSettings


class Target(unittest.TestCase):
    def setUp(self):
        self.t = tempfile.TemporaryDirectory()
        self.addCleanup(self.t.cleanup)
        self.r = Path(self.t.name)

    def test_tests_never_touch_the_real_desktop(self):
        self.assertNotEqual(shortcut.desktop().resolve(), (Path.home() / "Desktop").resolve())

    def test_source_copy_starts_with_dash_m_from_its_folder_with_the_apps_icon(self):
        with mock.patch.dict(os.environ, {"MODMANAGER_PYZ": ""}):
            exe, args, folder, icon = shortcut.target(self.r)
        self.assertEqual(args, "-m modmanager")
        self.assertTrue((Path(folder) / "modmanager" / "__init__.py").is_file())
        self.assertEqual(icon, f"{self.r / 'icon.ico'},0")
        self.assertEqual((self.r / "icon.ico").read_bytes()[:4], b"\x00\x00\x01\x00", "a real .ico, copied out of the app's files")
        self.assertNotEqual(Path(exe).name.lower(), "python.exe" if (Path(sys.executable).parent / "pythonw.exe").is_file() else "")

    def test_pyzw_copy_points_at_its_file(self):
        pyz = self.r / "dl" / "Mod-Manager-python.pyzw"
        with mock.patch.dict(os.environ, {"MODMANAGER_PYZ": str(pyz)}):
            exe, args, folder, icon = shortcut.target(self.r)
        self.assertEqual((args, folder), (f'"{pyz}"', str(pyz.parent)))

    def test_paths_go_in_through_the_environment_not_the_command(self):
        seen = {}

        def run(argv, env=None, **kw):
            seen.update(argv=argv, env=env)
            Path(env["RMM_LNK"]).write_text("lnk")
            return subprocess.CompletedProcess(argv, 0, "", "")
        with mock.patch.object(shortcut, "supported", return_value=True):
            lnk = shortcut.create(self.r, run=run)
        self.assertEqual(lnk.name, "Ronin Mod Manager.lnk")
        self.assertEqual(seen["env"]["RMM_LNK"], str(lnk))
        self.assertNotIn(str(lnk), " ".join(seen["argv"]))
        self.assertEqual(seen["argv"][:2], ["powershell", "-NoProfile"])

    def test_a_failure_says_why(self):
        run = lambda argv, **kw: subprocess.CompletedProcess(argv, 1, "", "Access is denied.\n")
        with mock.patch.object(shortcut, "supported", return_value=True), mock.patch.object(shortcut, "path", return_value=self.r / "x" / "a.lnk"):
            with self.assertRaisesRegex(ValueError, "Access is denied"):
                shortcut.create(self.r, run=run)

    @unittest.skipUnless(sys.platform == "win32", "Windows makes .lnk files")
    def test_windows_really_makes_it(self):
        with mock.patch.object(shortcut, "desktop", return_value=self.r / "Desk"):
            lnk = shortcut.create(self.r / "cfg")
        self.assertTrue(lnk.is_file())
        self.assertEqual(lnk.read_bytes()[:4], b"L\x00\x00\x00", "a Windows shortcut file")


class Asked(unittest.TestCase):
    def setUp(self):
        self.t = tempfile.TemporaryDirectory()
        self.addCleanup(self.t.cleanup)
        self.hub = Hub(settings=GlobalSettings(Path(self.t.name) / "g.json"), gamelist=[])

    def test_the_page_learns_whether_to_ask(self):
        info = self.hub.index()
        self.assertFalse(info["settings"]["shortcut_asked"])
        self.assertEqual(set(info["shortcut"]), {"supported", "exists", "path"})

    def test_no_thanks_is_remembered_and_makes_nothing(self):
        with mock.patch.object(shortcut, "create", side_effect=AssertionError("made one")):
            self.hub.desktop_shortcut(False)
        self.assertTrue(self.hub.settings.get()["shortcut_asked"])

    def test_yes_makes_it_and_is_remembered(self):
        with mock.patch.object(shortcut, "create") as create:
            self.hub.desktop_shortcut(True)
        create.assert_called_once()
        self.assertTrue(self.hub.settings.get()["shortcut_asked"])


if __name__ == "__main__":
    unittest.main()
