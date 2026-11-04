import os
import tempfile
import unittest
from pathlib import Path

from modmanager import launcher, update


class LauncherTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        os.environ["MODMANAGER_APP_DIR"] = str(self.tmp / "app")
        self.addCleanup(os.environ.pop, "MODMANAGER_APP_DIR", None)
        self.pyz = self.tmp / "dl" / "Mod-Manager-python.pyzw"
        self.pyz.parent.mkdir()
        self.pyz.write_bytes(b"PK-fake")

    def test_install_copies_the_app_and_writes_the_bat(self):
        bat = launcher.install(self.pyz)
        self.assertEqual(bat.name, "Ronin Mod Manager.bat")
        self.assertEqual((bat.parent / launcher.PYZ_NAME).read_bytes(), b"PK-fake")
        text = bat.read_bytes().decode("ascii")
        self.assertIn("\r\n", text)
        self.assertIn('"%HERE%Mod-Manager-python.pyzw" --update-first', text)
        self.assertTrue(launcher.installed())
        self.assertFalse(list(bat.parent.glob("*.part")))

    def test_installing_from_the_installed_copy_just_rewrites_the_bat(self):
        launcher.install(self.pyz)
        here = launcher.app_dir() / launcher.PYZ_NAME
        self.assertTrue(launcher.running_installed(here))
        launcher.install(here)
        self.assertEqual(here.read_bytes(), b"PK-fake")

    def test_source_copies_cannot_install(self):
        with self.assertRaises(ValueError):
            launcher.install(None)


class TestBuildVersion(unittest.TestCase):
    def fetch_for(self, body):
        return lambda url: (200, {"body": body, "published_at": "2026-11-02T00:00:00Z", "assets": []})

    def test_a_nightly_build_of_an_older_version_is_not_offered(self):
        r = update.check_nightly("aaaaaaa", fetch=self.fetch_for("build: bbbbbbb\nversion: 0.0.9\n"))
        self.assertFalse(r["update_available"])
        self.assertIn("older", r["message"])

    def test_same_or_newer_version_and_old_notes_without_a_version_are_offered(self):
        for body in ("build: bbbbbbb\nversion: %s\n" % update.__version__, "build: bbbbbbb\nversion: 99.0.0\n", "build: bbbbbbb\n"):
            self.assertTrue(update.check_nightly("aaaaaaa", fetch=self.fetch_for(body))["update_available"], body)


if __name__ == "__main__":
    unittest.main()
