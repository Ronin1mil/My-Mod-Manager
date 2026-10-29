import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from modmanager import errorlog, games
from tests.helpers import GameCase


class Log(unittest.TestCase):
    def test_writes_readable_entries_and_rotates(self):
        with tempfile.TemporaryDirectory() as d, mock.patch.dict(os.environ, {"MODMANAGER_LOG_DIR": d}):
            p = errorlog.write("page", "TypeError: boom", "at foo (app.js:1:2)", "ck3 app.js:1")
            self.assertEqual(Path(p), Path(d) / errorlog.LOG_NAME)
            txt = Path(p).read_text(encoding="utf-8")
            for want in ("[page] TypeError: boom", "at foo (app.js:1:2)", "where: ck3 app.js:1", "Mod Manager ", "Python "):
                self.assertIn(want, txt)
            Path(p).write_text("x" * (errorlog.MAX_BYTES + 1))
            errorlog.write("server", "second")
            self.assertTrue(Path(d, errorlog.LOG_NAME + ".1").is_file() or Path(d, "ModManager-errors.log.1").is_file())
            self.assertIn("second", Path(p).read_text())

    def test_never_raises_even_when_the_folder_is_unusable(self):
        with tempfile.TemporaryDirectory() as d:
            f = Path(d) / "afile"
            f.write_text("x")
            with mock.patch.dict(os.environ, {"MODMANAGER_LOG_DIR": str(f / "sub")}):
                self.assertEqual(errorlog.write("x", "y"), "")

    def test_default_location_is_documents_when_present(self):
        with tempfile.TemporaryDirectory() as h, mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop("MODMANAGER_LOG_DIR", None)
            (Path(h) / "Documents").mkdir()
            with mock.patch.object(errorlog.Path, "home", return_value=Path(h)), mock.patch.object(errorlog.sys, "platform", "linux"):
                self.assertEqual(errorlog.documents_dir(), Path(h) / "Documents")
            with mock.patch.object(errorlog.Path, "home", return_value=Path(h) / "nowhere"), mock.patch.object(errorlog.sys, "platform", "linux"):
                self.assertEqual(errorlog.documents_dir(), Path(h) / "nowhere")


class Http(GameCase):
    def setUp(self):
        super().setUp()
        p = mock.patch.dict(os.environ, {"MODMANAGER_LOG_DIR": str(self.r / "logs")})
        p.start()
        self.addCleanup(p.stop)

    def logtext(self):
        return (self.r / "logs" / errorlog.LOG_NAME).read_text(encoding="utf-8")

    def test_page_errors_are_logged_with_their_stack_and_capped(self):
        s, res, _ = self.post("/api/client-error", {"message": "Cannot read properties of null (reading 'playsets')",
                                                    "stack": "at render (app.js:151:20)", "where": "app.js:151", "game": "vic3"})
        self.assertEqual((s, res["logged"]), (200, True))
        t = self.logtext()
        self.assertIn("[page] Cannot read properties of null (reading 'playsets')", t)
        self.assertIn("at render (app.js:151:20)", t)
        self.assertIn("vic3 app.js:151", t)
        self.hub.client_errors = 200
        self.assertEqual(self.post("/api/client-error", {"message": "x" * 10})[1], {"logged": False})

    def test_garbage_report_is_harmless(self):
        self.assertEqual(self.post("/api/client-error", {"message": {"a": 1}, "stack": 5})[0], 200)

    def test_unexpected_server_error_is_json_with_log_path_and_traceback(self):
        app = self.hub.app("vic3")
        with mock.patch.object(app, "state", side_effect=RuntimeError("disk exploded")):
            s, res, _ = self.req("GET", "/api/state")
        self.assertEqual(s, 500)
        self.assertIn("RuntimeError: disk exploded", res["error"])
        self.assertTrue(res["log_file"].endswith(errorlog.LOG_NAME))
        t = self.logtext()
        self.assertIn("RuntimeError: disk exploded", t)
        self.assertIn("Traceback", t)
        self.assertIn("/api/vic3/state", t)

    def test_games_index_tells_the_page_where_the_log_is(self):
        self.assertTrue(self.req("GET", "/api/games")[1]["log_file"].endswith(errorlog.LOG_NAME))

    def test_fast_analyse_then_conflicts(self):
        pid = self.new_playset([])
        a = self.req("GET", f"/api/analyse/{pid}?fast=1")[1]
        self.assertEqual((a["pending"], a["conflicts"]), (True, []))
        c = self.req("GET", f"/api/conflicts/{pid}")[1]
        self.assertEqual((c["pending"], c["conflicts"]), (False, []))
        self.assertEqual(self.req("GET", "/api/conflicts/nope")[0], 404)
