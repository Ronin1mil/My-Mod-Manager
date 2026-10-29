"""The app window: which backend is used, how a closed window ends the app, and how an update restarts it."""
import os
import socket
import tempfile
import unittest
import urllib.request
from pathlib import Path
from unittest import mock

from modmanager import selfupdate, server, window


class Backends(unittest.TestCase):
    def test_browser_exe_can_be_forced_and_must_exist(self):
        with tempfile.TemporaryDirectory() as d:
            exe = Path(d) / "browser.exe"
            exe.write_text("x")
            with mock.patch.dict(os.environ, {"MODMANAGER_BROWSER_EXE": str(exe)}):
                self.assertEqual(window.chromium_path(), str(exe))
            with mock.patch.dict(os.environ, {"MODMANAGER_BROWSER_EXE": str(Path(d) / "missing.exe")}), \
                    mock.patch("shutil.which", return_value=None), mock.patch("pathlib.Path.is_file", return_value=False):
                self.assertIsNone(window.chromium_path())

    def test_webview_can_be_switched_off(self):
        with mock.patch.dict(os.environ, {"MODMANAGER_NO_WEBVIEW": "1"}):
            self.assertIsNone(window.pywebview_module())

    def test_probe_reports_without_opening_anything(self):
        p = window.probe()
        self.assertEqual(set(p), {"pywebview", "native", "native_error", "chromium", "frozen", "platform"})

    def test_pywebview_is_used_first_and_a_failure_falls_through(self):
        wv = mock.Mock()
        self.assertEqual(window.show("http://x/", pywebview=wv, chromium="/none"), "closed")
        wv.create_window.assert_called_once()
        wv.start.assert_called_once()
        bad = mock.Mock()
        bad.start.side_effect = RuntimeError("no WebView2")
        with mock.patch.object(window, "_run_app_window", return_value="closed") as app:
            self.assertEqual(window.show("http://x/", pywebview=bad, chromium="/edge"), "closed")
            app.assert_called_once()
        with mock.patch.object(window, "errorlog"):
            self.assertIsNone(window.show("http://x/", pywebview=bad, chromium=""))  # nothing left to try

    def test_app_window_detects_a_hand_off_to_a_running_browser(self):
        proc = mock.Mock()
        with mock.patch("subprocess.Popen", return_value=proc) as popen, \
                mock.patch("time.time", side_effect=[100.0, 100.5]):
            self.assertEqual(window._run_app_window("/edge", "http://x/", "T"), "detached")
        args = popen.call_args[0][0]
        self.assertEqual(args[0], "/edge")
        self.assertIn("--app=http://x/", args)
        self.assertTrue(any(a.startswith("--user-data-dir=") for a in args))
        with mock.patch("subprocess.Popen", return_value=proc), mock.patch("time.time", side_effect=[100.0, 160.0]):
            self.assertEqual(window._run_app_window("/edge", "http://x/", "T"), "closed")


class Serving(unittest.TestCase):
    def test_closing_the_window_ends_the_app(self):
        with socket.socket() as s:
            s.bind(("127.0.0.1", 0))
            port = s.getsockname()[1]
        seen = {}

        def fake_show(url):
            seen["url"] = url
            seen["status"] = urllib.request.urlopen(url, timeout=5).status  # the server is already answering
            return "closed"
        with mock.patch.object(window, "show", fake_show), mock.patch.dict(os.environ):
            server.serve(port, True, window=True)  # returns when the window closes
            self.assertEqual(os.environ["MODMANAGER_MODE"], "window")
        self.assertEqual(seen["status"], 200)
        self.assertEqual(seen["url"], f"http://127.0.0.1:{port}/")


class Restart(unittest.TestCase):
    def restart_args(self, mode):
        env = {} if mode is None else {"MODMANAGER_MODE": mode}
        with mock.patch.dict(os.environ, env, clear=False), mock.patch("subprocess.Popen") as popen:
            if mode is None:
                os.environ.pop("MODMANAGER_MODE", None)
            selfupdate.restart("/app/Mod-Manager.exe", ["--port", "9"])
        return popen.call_args[0][0]

    def test_a_window_reopens_after_an_update_but_a_browser_tab_does_not(self):
        self.assertEqual(self.restart_args("window"), ["/app/Mod-Manager.exe", "--port", "9"])
        self.assertEqual(self.restart_args("browser")[-1], "--no-browser")
        self.assertEqual(self.restart_args("none")[-1], "--no-browser")
        self.assertEqual(self.restart_args(None)[-1], "--no-browser")


if __name__ == "__main__":
    unittest.main()
