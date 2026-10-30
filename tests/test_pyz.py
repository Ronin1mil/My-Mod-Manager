"""The Python edition: one zip app started by python/py, no exe. It must run from its cache folder, serve the page,
know it can update itself, and replace itself through the same updater as the exe."""
import json
import os
import subprocess
import sys
import tempfile
import time
import unittest
import urllib.request
from pathlib import Path
from unittest import mock

from modmanager import selfupdate as su
from tools import build_pyz


class Built(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.d = Path(cls.tmp.name)
        cls.pyz = build_pyz.build(cls.d / "Mod-Manager-python.pyzw")
        cls.env = {**os.environ, "MODMANAGER_PYZ_CACHE": str(cls.d / "cache"), "MODMANAGER_CONFIG_DIR": str(cls.d / "cfg"),
                   "MODMANAGER_LOG_DIR": str(cls.d / "log"), "MODMANAGER_FETCH_LOGOS": "0"}
        cls.env.pop("MODMANAGER_PYZ", None)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def run_py(self, *args, path=None):
        return subprocess.run([sys.executable, str(path or self.pyz), *args], env=self.env, capture_output=True, text=True, timeout=60)

    def test_it_is_small_and_has_the_page_and_presets(self):
        import zipfile
        names = zipfile.ZipFile(self.pyz).namelist()
        self.assertIn("__main__.py", names)
        self.assertIn("modmanager/static/index.html", names)
        self.assertTrue(any(n.startswith("modmanager/presets/") for n in names))
        self.assertFalse([n for n in names if "__pycache__" in n])
        self.assertLess(self.pyz.stat().st_size, 5 * 1024 * 1024)

    def test_version_runs_from_the_cache_and_any_file_name_works(self):
        r = self.run_py("--version")
        self.assertEqual((r.returncode, r.stdout.strip()), (0, __import__("modmanager").__version__), r.stderr)
        caches = list((self.d / "cache").iterdir())
        self.assertEqual(len(caches), 1)
        self.assertTrue((caches[0] / "modmanager" / "static" / "index.html").is_file())
        new = self.d / "Mod-Manager-python.pyzw.new"       # the updater test-starts the download under this name
        new.write_bytes(self.pyz.read_bytes())
        self.assertEqual(self.run_py("--version", path=new).returncode, 0)
        self.assertEqual(len(list((self.d / "cache").iterdir())), 1)   # same bytes -> same cache folder

    def test_it_serves_the_page_and_can_update_itself(self):
        port = 18790 + os.getpid() % 100
        p = subprocess.Popen([sys.executable, str(self.pyz), "--no-browser", "--port", str(port)], env=self.env,
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        try:
            data = None
            for _ in range(60):
                try:
                    data = json.load(urllib.request.urlopen(f"http://127.0.0.1:{port}/api/games", timeout=2))
                    break
                except OSError:
                    time.sleep(0.25)
            self.assertIsNotNone(data, "the Python edition did not start")
            self.assertTrue(data["can_self_update"])
            page = urllib.request.urlopen(f"http://127.0.0.1:{port}/", timeout=5).read().decode()
            self.assertIn("Mod Manager", page)
        finally:
            p.kill()
            p.wait()


class Updating(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.f = Path(self.tmp.name) / "Mod-Manager-python.pyzw"
        self.f.write_bytes(b"old")
        p = mock.patch.dict(os.environ, {"MODMANAGER_PYZ": str(self.f)})
        p.start()
        self.addCleanup(p.stop)

    def test_it_is_recognised_and_asks_for_its_own_release_file(self):
        self.assertEqual(su.pyz_path(), self.f)
        self.assertTrue(su.can_self_update())
        self.assertEqual(su.platform_asset(), "Mod-Manager-python.pyzw")
        self.assertEqual(su.app_file(), self.f)
        self.assertEqual(su.Updater().exe, str(self.f))

    def test_a_missing_file_means_it_is_not_the_python_edition(self):
        self.f.unlink()
        self.assertIsNone(su.pyz_path())
        self.assertNotEqual(su.platform_asset(), "Mod-Manager-python.pyzw")

    def test_restart_starts_the_new_file_with_the_interpreter(self):
        with mock.patch.object(su.subprocess, "Popen") as popen:
            su.restart(self.f, ["--port", "9", "--no-browser"])
        args = popen.call_args[0][0]
        self.assertEqual(args[:2], [sys.executable, str(self.f)])
        self.assertIn("--port", args)

    def test_old_copy_is_removed_at_start(self):
        old = self.f.with_name(self.f.name + ".old")
        old.write_bytes(b"x")
        su.cleanup_old()
        self.assertFalse(old.exists())

    def test_the_test_start_uses_the_interpreter_too(self):
        new = self.f.with_name(self.f.name + ".new")
        new.write_bytes(b"not a zip app")
        ok, why = su.can_run(new)
        self.assertFalse(ok)   # python cannot run it, so the update would be refused before anything is swapped
        self.assertTrue(why)


if __name__ == "__main__":
    unittest.main()
