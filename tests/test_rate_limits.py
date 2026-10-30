"""Steam rate limits: steamcmd logs in once per batch, waits (with a countdown) when Steam limits it and tries again;
the Workshop web requests stop asking Steam until its limit is over and tell the page how long that is."""
import io
import subprocess
import tempfile
import time
import unittest
import urllib.error
from pathlib import Path
from unittest import mock

from modmanager import collections, games, workshop

LIMITED = "Logging in user 'acct' to Steam Public...FAILED (Rate Limit Exceeded)\n"


class Steamcmd(unittest.TestCase):
    def setUp(self):
        self.t = tempfile.TemporaryDirectory()
        self.addCleanup(self.t.cleanup)
        self.r = Path(self.t.name)
        self.exe = self.r / "steamcmd" / "steamcmd.exe"
        self.exe.parent.mkdir()
        self.exe.write_text("")
        self.content = workshop.content_dir(self.exe, games.CK3)

    def runner(self, limited_runs=0):
        calls = []

        def run(argv, **kw):
            calls.append(argv)
            if len(calls) <= limited_runs:
                return subprocess.CompletedProcess(argv, 5, LIMITED, "")
            out = []
            for wid in [argv[i + 2] for i, a in enumerate(argv) if a == "+workshop_download_item"]:
                (self.content / wid).mkdir(parents=True, exist_ok=True)
                out.append(f"Success. Downloaded item {wid} to x")
            return subprocess.CompletedProcess(argv, 0, "\n".join(out), "")
        return run, calls

    def wait(self, dl, jid, until=("done", "failed"), secs=5):
        end = time.time() + secs
        while time.time() < end:
            job = [j for j in dl.status() if j["id"] == jid][0]
            if job["state"] in until:
                return job
            time.sleep(0.005)
        self.fail(f"job never reached {until}")

    def test_one_login_per_batch_of_ten(self):
        run, calls = self.runner()
        dl = workshop.Downloads(games.CK3, run)
        ids = [str(1000 + i) for i in range(23)]
        job = self.wait(dl, dl.start(str(self.exe), "acct", ids)["id"])
        self.assertEqual(job["state"], "done")
        self.assertEqual([c.count("+login") for c in calls], [1, 1, 1])
        self.assertEqual([c.count("+workshop_download_item") for c in calls], [10, 10, 3])

    def test_a_rate_limit_waits_with_a_countdown_then_carries_on(self):
        run, calls = self.runner(limited_runs=1)
        dl = workshop.Downloads(games.CK3, run)
        with mock.patch.object(workshop, "RATE_LIMIT_WAIT", 0.3):
            jid = dl.start(str(self.exe), "acct", ["1", "2"])["id"]
            waiting = self.wait(dl, jid, until=("waiting",))
            self.assertIn("retry_in", waiting)
            self.assertNotIn("wake", waiting)
            self.assertEqual({i["state"] for i in waiting["items"].values()}, {"queued"})
            self.assertIn("rate limit", waiting["items"]["1"]["message"])
            job = self.wait(dl, jid)
        self.assertEqual(job["state"], "done")
        self.assertEqual(len(calls), 2)
        self.assertNotIn("retry_in", job)

    def test_retry_now_ends_the_wait(self):
        run, calls = self.runner(limited_runs=1)
        dl = workshop.Downloads(games.CK3, run)
        with mock.patch.object(workshop, "RATE_LIMIT_WAIT", 60):
            jid = dl.start(str(self.exe), "acct", ["1"])["id"]
            self.wait(dl, jid, until=("waiting",))
            dl.retry_now(jid)
            self.assertEqual(self.wait(dl, jid, secs=3)["state"], "done")
        with self.assertRaises(ValueError):
            dl.retry_now(jid)

    def test_gives_up_after_a_few_waits(self):
        run, calls = self.runner(limited_runs=99)
        dl = workshop.Downloads(games.CK3, run)
        with mock.patch.object(workshop, "RATE_LIMIT_WAIT", 0.01):
            job = self.wait(dl, dl.start(str(self.exe), "acct", ["1"])["id"])
        self.assertEqual(job["state"], "failed")
        self.assertEqual(len(calls), workshop.RATE_LIMIT_TRIES + 1)
        self.assertIn("rate limit", job["items"]["1"]["message"])


def http_error(code, retry_after=None):
    headers = {"Retry-After": str(retry_after)} if retry_after is not None else {}
    return urllib.error.HTTPError("https://api.steampowered.com/x", code, "Too Many Requests", headers, io.BytesIO(b""))


class WebApi(unittest.TestCase):
    def setUp(self):
        collections._limit.update(until=0.0, strikes=0)
        self.addCleanup(collections._limit.update, until=0.0, strikes=0)

    def test_429_uses_steams_wait_and_no_request_is_sent_until_it_is_over(self):
        with mock.patch("urllib.request.urlopen", side_effect=http_error(429, 120)) as op:
            with self.assertRaises(collections.RateLimited) as cm:
                collections.default_post("/x", {})
            self.assertEqual(cm.exception.seconds, 120)
            self.assertIn("2:00", str(cm.exception))
            with self.assertRaises(collections.RateLimited) as again:
                collections.default_post("/x", {})
            self.assertLessEqual(again.exception.seconds, 120)
        self.assertEqual(op.call_count, 1, "asking again during the limit only makes it longer")

    def test_without_a_retry_after_the_wait_grows(self):
        waits = []
        for _ in range(3):
            collections._limit["until"] = 0.0
            with mock.patch("urllib.request.urlopen", side_effect=http_error(429)):
                with self.assertRaises(collections.RateLimited) as cm:
                    collections.default_post("/x", {})
            waits.append(cm.exception.seconds)
        self.assertEqual(waits, [60, 120, 240])

    def test_other_errors_are_not_rate_limits(self):
        with mock.patch("urllib.request.urlopen", side_effect=http_error(500)):
            with self.assertRaises(ValueError) as cm:
                collections.default_post("/x", {})
        self.assertNotIsInstance(cm.exception, collections.RateLimited)
        self.assertEqual(collections._limit["until"], 0.0)


if __name__ == "__main__":
    unittest.main()
