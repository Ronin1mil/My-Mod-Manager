import hashlib
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from modmanager import selfupdate as su


def sums(name, data):
    return f"{hashlib.sha256(data).hexdigest()}  {name}\n"


class Parts(unittest.TestCase):
    def test_parse_sums_formats(self):
        h = "a" * 64
        self.assertEqual(su.parse_sums(f"{h}  Mod-Manager-linux\n{h.upper()} *dist/x.exe\njunk\n"),
                         {"Mod-Manager-linux": h, "x.exe": h})

    def test_download_only_from_github(self):
        for bad in ("http://github.com/x", "https://evil.example/x", "https://github.com.evil.io/x", "file:///etc/passwd",
                    "https://raw.githubusercontent.com/x"):  # the last is a CDN host: only reachable via a redirect
            with self.assertRaises(ValueError, msg=bad):
                su.download(bad, "/tmp/never")

    def test_redirects_only_to_github_hosts_and_token_is_not_forwarded(self):
        import urllib.request
        h = su._Redirects()
        req = urllib.request.Request("https://api.github.com/a", headers={"Authorization": "Bearer t"})
        with self.assertRaises(Exception):
            h.redirect_request(req, None, 302, "Found", {}, "https://evil.example/b")
        nr = h.redirect_request(req, None, 302, "Found", {}, "https://release-assets.githubusercontent.com/b")
        self.assertIsNone(nr.get_header("Authorization"))

    def test_swap_keeps_old_and_undoes_on_failure(self):
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            exe, new = d / "app", d / "app.new"
            exe.write_text("old"); new.write_text("new")
            old = su.swap(exe, new)
            self.assertEqual((exe.read_text(), old.read_text(), new.exists()), ("new", "old", False))
            exe.write_text("cur"); new.write_text("n2")
            with mock.patch.object(su.os, "replace", side_effect=[None, OSError("locked"), None]):
                with self.assertRaises(OSError):
                    su.swap(exe, new)


class ChildEnvironment(unittest.TestCase):
    """After an update the new copy must unpack its own files, not reuse the old copy's (a one-file PyInstaller app
    passes its unpack folder to children through the environment; 0.5.0 -> 0.8.0 then failed with No module named _sqlite3)."""

    def test_unpack_variables_are_dropped_and_reset_is_requested(self):
        import os
        from unittest import mock
        with mock.patch.dict(os.environ, {"_MEIPASS2": "C:/old", "_PYI_APPLICATION_HOME_DIR": "C:/old", "_PYI_ARCHIVE_FILE": "x",
                                          "MODMANAGER_MODE": "window", "PATH": os.environ.get("PATH", "")}):
            env = su.child_environment()
        self.assertFalse([k for k in env if k == "_MEIPASS2" or k.startswith("_PYI_")])
        self.assertEqual(env["PYINSTALLER_RESET_ENVIRONMENT"], "1")
        self.assertEqual(env["MODMANAGER_RESTARTED"], "1")
        self.assertEqual(env["MODMANAGER_MODE"], "window")  # the window mode is kept


class CanRun(unittest.TestCase):
    def test_a_program_that_starts_passes_and_a_missing_or_failing_one_does_not(self):
        import sys
        self.assertEqual(su.can_run(sys.executable), (True, ""))
        ok, why = su.can_run(Path(sys.executable).with_name("no-such-program"))
        self.assertFalse(ok)
        self.assertTrue(why)
        if sys.platform != "win32":
            with tempfile.TemporaryDirectory() as t:
                f = Path(t) / "fails"
                f.write_text("#!/bin/sh\nexit 5\n")
                f.chmod(0o755)
                self.assertEqual(su.can_run(f), (False, "it ended with exit code 5"))


class Flow(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.d = Path(self.tmp.name)
        self.exe = self.d / "app"
        self.exe.write_text("old-version")
        self.addCleanup(self.tmp.cleanup)
        self.payload = b"NEW-APP-BYTES"
        self.restarted, self.exited = [], []
        self.asset = su.platform_asset()

    def info(self, **kw):
        a = lambda n: {"name": n, "url": f"https://github.com/Ronin1mil/My-Mod-Manager/releases/download/v9/{n}", "api_url": "", "size": 1}
        return {"update_available": True, "latest": "9.0.0", "assets": [a(self.asset), a(su.SUMS_NAME)], **kw}

    def dl_factory(self, payload=None, sum_text=None):
        payload = self.payload if payload is None else payload
        def dl(url, dest, limit, token=None):
            data = (sum_text if sum_text is not None else sums(self.asset, self.payload)).encode() if url.endswith(su.SUMS_NAME) else payload
            Path(dest).write_bytes(data)
            return hashlib.sha256(data).hexdigest()
        return dl

    def updater(self, info=None, dl=None):
        return su.Updater(check=lambda: info or self.info(), dl=dl or self.dl_factory(), exe=str(self.exe), argv=["--port", "9"],
                          restarter=lambda e, a: self.restarted.append((str(e), a)), exiter=lambda: self.exited.append(1))

    def test_happy_path_replaces_and_restarts(self):
        u = self.updater()
        self.assertEqual(u.start(run_async=False)["status"], "restarting")
        self.assertEqual(self.exe.read_bytes(), self.payload)
        self.assertEqual((self.d / "app.old").read_text(), "old-version")
        self.assertEqual(self.restarted, [(str(self.exe), ["--port", "9"])])

    def test_a_file_windows_refuses_to_start_is_never_swapped_in(self):
        u = su.Updater(check=lambda: self.info(), dl=self.dl_factory(), exe=str(self.exe), argv=[],
                       restarter=lambda e, a: self.restarted.append(1), exiter=lambda: self.exited.append(1),
                       verify=lambda p: (False, "[WinError 4551] An Application Control policy has blocked this file"))
        st = u.start(run_async=False)
        self.assertEqual(st["status"], "error")
        self.assertIn("4551", st["message"])
        self.assertIn("Nothing was changed", st["message"])
        self.assertEqual(self.exe.read_text(), "old-version")
        self.assertFalse((self.d / "app.new").exists() or (self.d / "app.old").exists() or self.restarted)

    def test_the_new_file_is_test_started_before_the_swap(self):
        seen = []
        u = su.Updater(check=lambda: self.info(), dl=self.dl_factory(), exe=str(self.exe), argv=[],
                       restarter=lambda e, a: None, exiter=lambda: self.exited.append(1),
                       verify=lambda p: seen.append((Path(p).name, self.exe.read_text())) or (True, ""))
        self.assertEqual(u.start(run_async=False)["status"], "restarting")
        self.assertEqual(seen, [("app.new", "old-version")])   # the old program was still in place

    def test_a_new_copy_that_cannot_start_is_rolled_back(self):
        def boom(e, a):
            raise OSError("[WinError 4551] blocked")
        u = su.Updater(check=lambda: self.info(), dl=self.dl_factory(), exe=str(self.exe), argv=[], restarter=boom,
                       exiter=lambda: self.exited.append(1), verify=lambda p: (True, ""))
        st = u.start(run_async=False)
        self.assertEqual(st["status"], "error")
        self.assertIn("put back", st["message"])
        self.assertEqual(self.exe.read_text(), "old-version")
        self.assertEqual(sorted(p.name for p in self.d.iterdir()), ["app"])   # no .old/.new/.bad left over
        self.assertEqual(self.exited, [])                                     # this copy keeps running

    def test_a_new_copy_that_ends_at_once_is_rolled_back(self):
        class Dead:
            returncode = 3
            def poll(self):
                return 3
        u = su.Updater(check=lambda: self.info(), dl=self.dl_factory(), exe=str(self.exe), argv=[],
                       restarter=lambda e, a: Dead(), exiter=lambda: self.exited.append(1), verify=lambda p: (True, ""))
        st = u.start(run_async=False)
        self.assertEqual(st["status"], "error")
        self.assertEqual(self.exe.read_text(), "old-version")
        self.assertEqual(self.exited, [])

    def test_a_locked_old_copy_does_not_stop_the_next_update(self):
        """A leftover <exe>.old can be a program that is still running (an update whose restart failed): it cannot be
        deleted, and the swap used to fail with "Access is denied" every time after that."""
        (self.d / "app.old").write_text("still running")
        real = Path.unlink
        def locked(self_, *a, **k):
            if self_.name == "app.old":
                raise PermissionError(5, "Access is denied")
            return real(self_, *a, **k)
        u = self.updater()
        with mock.patch.object(Path, "unlink", locked):
            self.assertEqual(u.start(run_async=False)["status"], "restarting")
        self.assertEqual(self.exe.read_bytes(), self.payload)
        self.assertEqual((self.d / "app.old1").read_text(), "old-version")
        self.assertEqual((self.d / "app.old").read_text(), "still running")   # untouched

    def test_the_test_build_channel_uses_its_own_check(self):
        calls = []
        nightly = self.info(latest="test build abc1234")
        u = su.Updater(check=lambda: calls.append("stable") or self.info(), check_nightly_=lambda: calls.append("nightly") or nightly,
                       dl=self.dl_factory(), exe=str(self.exe), argv=[],
                       restarter=lambda e, a: self.restarted.append(1), exiter=lambda: self.exited.append(1))
        st = u.start(run_async=False, channel="nightly")
        self.assertEqual((calls, st["status"]), (["nightly"], "restarting"))
        self.assertIn("test build abc1234", st["message"])
        self.exe.write_text("old-version")  # the next run is a normal one again
        u.start(run_async=False)
        self.assertEqual(calls, ["nightly", "stable"])

    def test_the_release_channel_installs_the_newest_release_even_when_the_running_version_is_not_older(self):
        calls = []
        u = su.Updater(check=lambda: calls.append("stable") or self.info(), check_nightly_=lambda: calls.append("nightly") or self.info(),
                       dl=self.dl_factory(), exe=str(self.exe), argv=[],
                       restarter=lambda e, a: self.restarted.append(1), exiter=lambda: self.exited.append(1))
        u.check_release = lambda: calls.append("release") or self.info(latest="0.9.1")
        st = u.start(run_async=False, channel="release")
        self.assertEqual((calls, st["status"]), (["release"], "restarting"))

    def test_checksum_mismatch_changes_nothing(self):
        u = self.updater(dl=self.dl_factory(payload=b"TAMPERED"))
        st = u.start(run_async=False)
        self.assertEqual(st["status"], "error")
        self.assertIn("checksum", st["message"])
        self.assertEqual(self.exe.read_text(), "old-version")
        self.assertFalse((self.d / "app.new").exists() or self.restarted)

    def test_missing_or_unlisted_hash_is_refused(self):
        for text in ("", sums("other-file", b"x")):
            u = self.updater(dl=self.dl_factory(sum_text=text))
            self.assertEqual(u.start(run_async=False)["status"], "error")
            self.assertEqual(self.exe.read_text(), "old-version")
        i = self.info(); i["assets"] = [a for a in i["assets"] if a["name"] != su.SUMS_NAME]
        self.assertEqual(self.updater(info=i).start(run_async=False)["status"], "error")

    def test_up_to_date_and_source_installs(self):
        self.assertEqual(self.updater(info={"update_available": False, "message": "You are up to date."}).start(run_async=False)["status"], "current")
        with self.assertRaisesRegex(ValueError, "source"):
            su.Updater().start()

    def test_download_error_is_reported_not_raised(self):
        def boom(*a, **k):
            raise ValueError("Could not download the update: offline")
        st = self.updater(dl=boom).start(run_async=False)
        self.assertEqual((st["status"], self.exe.read_text()), ("error", "old-version"))
        self.assertIn("offline", st["message"])


class NightlyCheck(unittest.TestCase):
    def rel(self, body="Test build.\n\nbuild: abc1234\n", assets=True):
        base = "https://github.com/Ronin1mil/My-Mod-Manager/releases/download/test-build/"
        a = [{"id": 5, "name": "Mod-Manager-windows.exe", "size": 3, "browser_download_url": base + "Mod-Manager-windows.exe"},
             {"id": 6, "name": "evil.exe", "size": 3, "browser_download_url": "https://evil.example/x.exe"}] if assets else []
        return (200, {"body": body, "published_at": "2026-10-29T10:00:00Z", "prerelease": True, "assets": a})

    def test_a_newer_build_is_offered_and_foreign_links_are_dropped(self):
        from modmanager import update
        r = update.check_nightly("0000000", fetch=lambda u: self.rel())
        self.assertEqual((r["update_available"], r["build"], r["status"]), (True, "abc1234", "update"))
        self.assertEqual([a["name"] for a in r["assets"]], ["Mod-Manager-windows.exe"])
        self.assertFalse(update.check_nightly("abc1234", fetch=lambda u: self.rel())["update_available"])  # already on it

    def test_missing_release_unreadable_body_and_network_trouble_are_reported(self):
        from modmanager import update
        self.assertEqual(update.check_nightly("", fetch=lambda u: (404, None))["status"], "no_releases")
        self.assertEqual(update.check_nightly("", fetch=lambda u: self.rel(body="no id here"))["update_available"], False)
        def down(u):
            raise OSError("offline")
        self.assertEqual(update.check_nightly("", fetch=down)["status"], "unreachable")

    def test_a_test_build_is_not_pushed_back_to_the_release_of_its_own_version(self):
        from unittest import mock
        from modmanager import update
        with mock.patch.object(update, "BUILD", "abc1234"):
            self.assertFalse(update.is_newer(update.__version__, update.stable_current()))
            self.assertTrue(update.is_newer("99.0.0", update.stable_current()))   # a higher release number still counts

    def test_going_back_to_the_release_works_from_any_version(self):
        from modmanager import update
        rel = {"tag_name": "v0.9.1", "html_url": "https://github.com/Ronin1mil/My-Mod-Manager/releases/tag/v0.9.1", "body": "",
               "published_at": "2026-10-30T00:00:00Z", "assets": []}
        r = update.check_for_update("0.0.0", lambda u: (200, rel))
        self.assertTrue(r["update_available"])
