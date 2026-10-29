import json
import os
import stat
import tempfile
import unittest
from unittest import mock
import zipfile
from pathlib import Path

from modmanager import install

META = json.dumps({"name": "Cool Mod", "version": "1.2", "supported_game_version": "1.7.*"})


def zipf(path, entries):
    with zipfile.ZipFile(path, "w") as z:
        for name, data in entries.items():
            z.writestr(name, data)
    return path


class T(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.r = Path(self.tmp.name)
        _p = mock.patch.dict(os.environ, {"MODMANAGER_CONFIG_DIR": str(self.r / "cfg")})
        _p.start()
        self.addCleanup(_p.stop)
        self.user = self.r / "user"

    def tearDown(self):
        self.tmp.cleanup()

    def test_safe_relative(self):
        self.assertEqual(install.safe_relative("a\\b/./c.txt"), "a/b/c.txt")
        for bad in ("../x", "a/../../x", "/etc/passwd", "C:/x", "a/CON", "a/nul.txt", "a/b:stream", "a/b.", "a\0b"):
            with self.assertRaises(install.UnsafeArchive, msg=bad):
                install.safe_relative(bad)

    def test_installs_and_upgrades_with_backup(self):
        a = zipf(self.r / "m.zip", {"Cool/.metadata/metadata.json": META, "Cool/common/x.txt": "v1"})
        rep = install.install_archive(a, self.user, "cool.zip")
        self.assertEqual(rep["installed"][0]["name"], "Cool Mod")
        self.assertFalse(rep["installed"][0]["upgraded"])
        desc = (self.user / "mod/Cool.mod").read_text()
        self.assertIn('path="mod/Cool"', desc)
        self.assertIn('supported_version="1.7.*"', desc)
        b = zipf(self.r / "m2.zip", {"Cool/.metadata/metadata.json": META, "Cool/common/x.txt": "v2"})
        self.assertTrue(install.install_archive(b, self.user, "cool.zip")["installed"][0]["upgraded"])
        self.assertEqual((self.user / "mod/Cool/common/x.txt").read_text(), "v2")
        backups = list((self.r / "cfg/backups").iterdir())
        self.assertEqual((backups[0] / "common/x.txt").read_text(), "v1")

    def test_mod_at_archive_root_uses_archive_name(self):
        a = zipf(self.r / "m.zip", {".metadata/metadata.json": META, "common/x.txt": "x"})
        self.assertEqual(install.install_archive(a, self.user, "My Mod.zip")["installed"][0]["folder"], "My Mod")

    def test_rejects_unsafe_archives_and_writes_nothing(self):
        cases = {
            "zip-slip": {"../evil.txt": "x", "M/.metadata/metadata.json": META},
            "exe": {"M/.metadata/metadata.json": META, "M/run.exe": "MZ"},
            "script": {"M/.metadata/metadata.json": META, "M/a.bat": "x"},
            "not a mod": {"readme.txt": "hi"},
        }
        for label, entries in cases.items():
            with self.assertRaises(ValueError, msg=label):
                install.install_archive(zipf(self.r / "bad.zip", entries), self.user, "bad.zip")
        self.assertFalse((self.r / "evil.txt").exists())
        self.assertEqual(list((self.user / "mod").glob("*")), [])
        with self.assertRaises(ValueError):
            install.install_archive(self.r / "x", self.user, "mod.rar")

    def test_rejects_symlink_entries(self):
        p = self.r / "s.zip"
        with zipfile.ZipFile(p, "w") as z:
            zi = zipfile.ZipInfo("M/link")
            zi.external_attr = (stat.S_IFLNK | 0o777) << 16
            z.writestr(zi, "/etc/passwd")
            z.writestr("M/.metadata/metadata.json", META)
        with self.assertRaises(install.UnsafeArchive):
            install.install_archive(p, self.user, "s.zip")

    def test_limits(self):
        old = install.MAX_ENTRIES, install.MAX_TOTAL
        try:
            install.MAX_ENTRIES = 2
            with self.assertRaises(install.UnsafeArchive):
                install.install_archive(zipf(self.r / "a.zip", {f"M/f{i}": "x" for i in range(5)}), self.user, "a.zip")
            install.MAX_ENTRIES, install.MAX_TOTAL = old[0], 10
            with self.assertRaises(install.UnsafeArchive):
                install.install_archive(zipf(self.r / "b.zip", {"M/.metadata/metadata.json": META}), self.user, "b.zip")
        finally:
            install.MAX_ENTRIES, install.MAX_TOTAL = old
        p = self.r / "bomb.zip"
        with zipfile.ZipFile(p, "w", zipfile.ZIP_DEFLATED) as z:
            z.writestr("M/.metadata/metadata.json", META)
            z.writestr("M/big.bin", b"\0" * (50 * 1024**2))
        with self.assertRaises(install.UnsafeArchive):
            install.install_archive(p, self.user, "bomb.zip")

    def test_garbage_file(self):
        (self.r / "g.zip").write_bytes(b"not a zip")
        with self.assertRaises(install.UnsafeArchive):
            install.install_archive(self.r / "g.zip", self.user, "g.zip")

    def test_uninstall_moves_to_backup_and_stays_inside_mod_dir(self):
        install.install_archive(zipf(self.r / "m.zip", {"Cool/.metadata/metadata.json": META}), self.user, "c.zip")
        from modmanager import scan
        mods = scan.scan_mods(self.user)
        m = mods["local:Cool"]
        dest = install.uninstall(self.user, m)
        self.assertFalse((self.user / "mod/Cool").exists() or (self.user / "mod/Cool.mod").exists())
        self.assertTrue(Path(dest).is_dir() and Path(dest + ".mod").is_file())
        with self.assertRaises(ValueError):
            install.uninstall(self.user, {**m, "root": str(self.r)})
        with self.assertRaises(ValueError):
            install.uninstall(self.user, {**m, "source": "workshop"})


if __name__ == "__main__":
    unittest.main()
