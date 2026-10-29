"""The timestamped activity log (what was done, how long it took)."""
import os
import re
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from modmanager import games, perflog
from tests.helpers import GameCase, mkmod


class Log(unittest.TestCase):
    def setUp(self):
        t = tempfile.TemporaryDirectory()
        self.addCleanup(t.cleanup)
        self.dir = Path(t.name)
        p = mock.patch.dict(os.environ, {"MODMANAGER_LOG_DIR": str(self.dir), "MODMANAGER_ACTIVITY_LOG": "1"})
        p.start()
        self.addCleanup(p.stop)
        perflog._size = None
        self.file = perflog.log_path()

    def text(self):
        return self.file.read_text(encoding="utf-8")

    def test_lines_have_a_timestamp_and_thread(self):
        perflog.log("hello")
        self.assertRegex(self.text(), r"^\d{4}-\d\d-\d\d \d\d:\d\d:\d\d\.\d{3} \[MainThread\] hello\n$")

    def test_a_timed_block_writes_start_and_end_with_milliseconds(self):
        with perflog.timed("scan", mods=3) as t:
            t.note(found=2)
        lines = self.text().splitlines()
        self.assertRegex(lines[0], r"\] > scan mods=3$")
        self.assertRegex(lines[1], r"\] < scan [\d.]+ ms mods=3 found=2$")

    def test_quiet_blocks_only_write_the_end_and_failures_are_marked(self):
        with perflog.timed("fast", quiet=True):
            pass
        with self.assertRaises(ValueError):
            with perflog.timed("boom"):
                raise ValueError("x")
        text = self.text()
        self.assertNotIn("> fast", text)
        self.assertIn("< fast", text)
        self.assertRegex(text, r"< boom [\d.]+ ms FAILED ValueError")

    def test_a_hang_is_visible_as_a_start_without_an_end(self):
        perflog.log("> stuck")
        self.assertNotIn("< stuck", self.text())

    def test_off_by_default_in_a_release_and_on_for_test_builds(self):
        with mock.patch.dict(os.environ, {"MODMANAGER_ACTIVITY_LOG": ""}):
            with mock.patch.object(perflog, "BUILD", ""):
                self.assertFalse(perflog.enabled())
            with mock.patch.object(perflog, "BUILD", "abc1234"):
                self.assertTrue(perflog.enabled())
        with mock.patch.dict(os.environ, {"MODMANAGER_ACTIVITY_LOG": "0"}), mock.patch.object(perflog, "BUILD", "abc1234"):
            self.assertFalse(perflog.enabled())

    def test_the_file_rotates_and_a_bad_folder_never_raises(self):
        with mock.patch.object(perflog, "MAX_BYTES", 200):
            for i in range(30):
                perflog.log(f"line {i} " + "x" * 20)
        self.assertTrue(self.file.with_name(self.file.name + ".1").is_file())
        self.assertLess(self.file.stat().st_size, 400)
        blocker = self.dir / "file"
        blocker.write_text("not a folder")
        with mock.patch.dict(os.environ, {"MODMANAGER_LOG_DIR": str(blocker / "sub")}):
            perflog._size = None
            perflog.log("goes nowhere")  # must not raise


class Instrumented(GameCase):
    GAME = games.VIC3

    def setUp(self):
        super().setUp()
        p = mock.patch.dict(os.environ, {"MODMANAGER_ACTIVITY_LOG": "1", "MODMANAGER_LOG_DIR": str(self.r / "logs")})
        p.start()
        self.addCleanup(p.stop)
        perflog._size = None

    def test_requests_and_the_slow_steps_are_logged(self):
        mkmod(self.user(), "A", "A")
        pid = self.new_playset(["local:A"])
        self.req("GET", f"/api/conflicts/{pid}")
        self.req("GET", f"/api/analyse/{pid}?fast=1")
        self.req("GET", "/api/state")
        text = perflog.log_path().read_text(encoding="utf-8")
        for want in (r"> GET /api/vic3/state", r"< GET /api/vic3/state [\d.]+ ms status=200", r"> POST /api/vic3/playsets",
                     r"conflict scan", r"load-order check"):
            self.assertRegex(text, want)
        self.assertNotRegex(text, r"GET /(index|app\.js|style\.css)")  # the page's own files are not logged
