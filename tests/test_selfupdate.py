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
