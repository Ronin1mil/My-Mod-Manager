"""Presets (curated playsets), Workshop downloads, and their HTTP endpoints."""
import json
import os
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

from modmanager import games, presets, scan, workshop
from tests.helpers import GameCase, mkmod, mkworkshop


def doc(**kw):
    d = {"format": "modmanager-preset", "id": "my-set", "game": "ck3", "name": "My set",
         "mods": [{"workshop_id": "111", "name": "One"}, {"workshop_id": 222, "name": "Two", "enabled": False}]}
    d.update(kw)
    return d


class Validation(unittest.TestCase):
    def test_valid_preset_is_cleaned(self):
        p = presets.validate(doc(), "ck3")
        self.assertEqual([(m["workshop_id"], m["enabled"]) for m in p["mods"]], [("111", True), ("222", False)])
        self.assertEqual(p["status"], "unverified")  # default until someone has checked the ids

    def test_duplicates_collapse_and_status_is_restricted(self):
        p = presets.validate(doc(status="whatever", mods=[{"workshop_id": "1"}, {"workshop_id": 1}]), "ck3")
        self.assertEqual((len(p["mods"]), p["status"]), (1, "unverified"))
        self.assertEqual(presets.validate(doc(status="verified"), "ck3")["status"], "verified")

    def test_bad_presets_are_rejected(self):
        bad = [None, [], {}, doc(format="x"), doc(id="Bad Id"), doc(id="../x"), doc(id=""), doc(game="eu5"), doc(game=5),
               doc(name=""), doc(name="x" * 61), doc(mods=[]), doc(mods="x"), doc(mods=[{"workshop_id": "abc"}]),
               doc(mods=[{"workshop_id": "1; rm"}]), doc(mods=[{"name": "no id"}]), doc(mods=[{"workshop_id": True}]),
               doc(mods=[{"workshop_id": "1", "name": 5}]), doc(mods=[{"workshop_id": "1", "note": "n" * 301}]),
               doc(mods=[{"workshop_id": str(i)} for i in range(301)]), doc(mods=[{"workshop_id": "9" * 21}])]
        for b in bad:
            with self.assertRaises(ValueError, msg=str(b)[:70]):
                presets.validate(b, "ck3")

    def test_the_built_in_files_are_valid_for_their_game(self):
        files = sorted((Path(presets.BUILTIN)).glob("*.json"))
        self.assertTrue(files)
        for f in files:
            d = json.loads(f.read_text(encoding="utf-8"))
            presets.validate(d, d["game"])
            self.assertIn(d["game"], games.GAMES)
            self.assertTrue(d["id"].startswith(d["game"]), f.name)

    def test_rice_stack_draft_is_labelled_unverified(self):
        p = presets.load_all(games.CK3)["ck3-rice-stack"]
        self.assertEqual(p["status"], "unverified")
        self.assertIn("2273832430", [m["workshop_id"] for m in p["mods"]])
        self.assertIn("unverified", p["description"])
        self.assertNotIn("ck3-rice-stack", presets.load_all(games.EU5))  # presets are per game


class Loading(unittest.TestCase):
    def setUp(self):
        self.t = tempfile.TemporaryDirectory()
        self.r = Path(self.t.name)
        self.addCleanup(self.t.cleanup)
        p = mock.patch.dict(os.environ, {"MODMANAGER_CONFIG_DIR": str(self.r)})
        p.start()
        self.addCleanup(p.stop)

    def test_user_presets_load_and_override_built_in_ones(self):
        d = self.r / "ck3/presets"
        d.mkdir(parents=True)
        (d / "mine.json").write_text(json.dumps(doc()))
        (d / "ck3-rice-stack.json").write_text(json.dumps(doc(id="ck3-rice-stack", name="My RICE")))
        got = presets.load_all(games.CK3)
        self.assertEqual((got["my-set"]["builtin"], got["ck3-rice-stack"]["name"], got["ck3-rice-stack"]["builtin"]),
                         (False, "My RICE", False))

    def test_broken_files_are_skipped_not_fatal(self):
        d = self.r / "ck3/presets"
        d.mkdir(parents=True)
        (d / "a.json").write_text("{nope")
        (d / "b.json").write_text(json.dumps(doc(game="eu5")))
        (d / "c.json").write_text("x" * (presets.MAX_FILE + 1))
        (d / "d.json").write_bytes(b"\xff\xfe\x00")
        self.assertTrue({"ck3-rice-stack", "ck3-culture-expanded", "ck3-princes-of-darkness"} <= set(presets.load_all(games.CK3)))

    def test_save_user_preset_roundtrip_and_playset_conversion(self):
        mkworkshop(self.r / "ws", 111, "One")
        mods = scan.scan_mods(None, self.r / "ws")
        ps = {"mods": ["ws:111", "local:Z", "ws:222"], "disabled": ["ws:222"]}
        d = presets.from_playset(games.CK3, ps, mods, "from-ps", "From playset")
        self.assertEqual([(m["workshop_id"], m["enabled"]) for m in d["mods"]], [("111", True), ("222", False)])
        presets.save_user_preset(games.CK3, d)
        self.assertEqual(presets.load_all(games.CK3)["from-ps"]["name"], "From playset")
        with self.assertRaises(ValueError):
            presets.from_playset(games.CK3, {"mods": ["local:Z"], "disabled": []}, mods, "x", "x")
        with self.assertRaises(ValueError):
            presets.save_user_preset(games.CK3, {**d, "id": "../escape"})
        self.assertFalse((self.r / "escape.json").exists())

    def test_to_playset_args_marks_missing_and_uses_installed_ids(self):
        mkworkshop(self.r / "ws", 111, "One")
        mods = scan.scan_mods(None, self.r / "ws")
        ids, off, missing = presets.to_playset_args(presets.validate(doc(), "ck3"), mods)
        self.assertEqual((ids, off, missing), (["ws:111", "ws:222"], ["ws:222"], [{"workshop_id": "222", "name": "Two"}]))
        s = presets.summarize(presets.validate(doc(), "ck3"), mods)
        self.assertEqual((s["installed"], s["total"]), (1, 2))


class FakeRun:
    """Stands in for subprocess.run: records argv, and 'downloads' by creating the folder."""

    def __init__(self, content, fail=()):
        self.calls, self.content, self.fail = [], content, set(fail)

    def __call__(self, argv, **kw):
        self.calls.append((argv, kw))
        wid = argv[argv.index("+workshop_download_item") + 2]
        if wid in self.fail:
            return subprocess.CompletedProcess(argv, 8, "ERROR! Download item failed (Failure).\n", "")
        (self.content / wid).mkdir(parents=True, exist_ok=True)
        return subprocess.CompletedProcess(argv, 0, f'Success. Downloaded item {wid} to "x"\n', "")


class Downloads(unittest.TestCase):
    def setUp(self):
        self.t = tempfile.TemporaryDirectory()
        self.r = Path(self.t.name)
        self.addCleanup(self.t.cleanup)
        self.exe = self.r / "steamcmd" / "steamcmd.sh"
        self.exe.parent.mkdir()
        self.exe.write_text("#!/bin/sh\n")
        self.content = workshop.content_dir(self.exe, games.CK3)

    def wait(self, dl, jid, secs=5):
        end = time.time() + secs
        while time.time() < end:
            job = [j for j in dl.status() if j["id"] == jid][0]
            if job["state"] in ("done", "failed"):
                return job
            time.sleep(0.01)
        self.fail("download did not finish")

    def test_ids_are_validated(self):
        self.assertEqual(workshop.clean_ids(["1", 2, "1"]), ["1", "2"])
        for bad in ([], "1", None, ["x"], ["1 2"], ["1;ls"], [True], [""], ["9" * 21], [str(i) for i in range(301)], [-1]):
            with self.assertRaises(ValueError, msg=str(bad)[:40]):
                workshop.clean_ids(bad)

    def test_steam_pages_open_via_the_given_opener_only(self):
        seen = []
        urls = workshop.open_pages(["123", "456"], seen.append, delay=0)
        self.assertEqual(seen, ["steam://url/CommunityFilePage/123", "steam://url/CommunityFilePage/456"])
        self.assertEqual(urls, seen)
        with self.assertRaises(ValueError):
            workshop.open_pages(["1/../../x"], seen.append, delay=0)
        self.assertEqual(len(seen), 2)

    def test_steamcmd_is_validated_before_anything_runs(self):
        run = FakeRun(self.content)
        dl = workshop.Downloads(games.CK3, run)
        for exe, user in (("", "bob"), (self.r / "nope", "bob"), (self.exe, ""), (self.exe, "bad name"), (self.exe, "a;b"), (self.exe, "x")):
            with self.assertRaises(ValueError, msg=(exe, user)):
                dl.start(str(exe), user, ["1"])
        self.assertEqual(run.calls, [])

    def test_successful_download_runs_exact_argv_without_a_shell(self):
        run = FakeRun(self.content)
        dl = workshop.Downloads(games.CK3, run)
        job = dl.start(str(self.exe), "my_account", ["111", "222"])
        done = self.wait(dl, job["id"])
        self.assertEqual(done["state"], "done")
        self.assertEqual([c[0] for c in run.calls], [
            [str(self.exe), "+login", "my_account", "+workshop_download_item", "1158310", "111", "+quit"],
            [str(self.exe), "+login", "my_account", "+workshop_download_item", "1158310", "222", "+quit"]])
        for _, kw in run.calls:
            self.assertFalse(kw.get("shell"))
            self.assertEqual(kw["cwd"], str(self.exe.parent))
            self.assertGreater(kw["timeout"], 0)
        self.assertTrue((self.content / "111").is_dir())

    def test_failures_are_reported_per_item_and_do_not_stop_the_rest(self):
        run = FakeRun(self.content, fail={"111"})
        dl = workshop.Downloads(games.CK3, run)
        done = self.wait(dl, dl.start(str(self.exe), "acct", ["111", "222"])["id"])
        self.assertEqual((done["state"], done["items"]["111"]["state"], done["items"]["222"]["state"]), ("failed", "failed", "done"))
        self.assertIn("failed", done["items"]["111"]["message"].lower())

    def test_no_saved_login_stops_at_once_and_says_how_to_log_in(self):
        out = "Logging in user 'acct' to Steam Public...\nCached credentials not found.\nFAILED (No Connection)\n"
        run = mock.Mock(return_value=subprocess.CompletedProcess([], 5, stdout=out, stderr=""))
        dl = workshop.Downloads(games.CK3, run)
        done = self.wait(dl, dl.start(str(self.exe), "acct", ["111", "222", "333"])["id"])
        self.assertEqual(run.call_count, 1, "the other items would fail the same way")
        self.assertEqual({i["state"] for i in done["items"].values()}, {"failed"})
        msg = done["items"]["333"]["message"]
        self.assertIn("+login acct", msg)
        self.assertIn("not logged in", msg)
        self.assertNotIn("password=", msg.lower())

    def test_missing_binary_and_timeouts_become_item_failures(self):
        for exc in (OSError("cannot execute"), subprocess.TimeoutExpired("x", 1)):
            dl = workshop.Downloads(games.CK3, mock.Mock(side_effect=exc))
            done = self.wait(dl, dl.start(str(self.exe), "acct", ["5"])["id"])
            self.assertEqual(done["items"]["5"]["state"], "failed")

    def test_success_text_without_the_folder_is_not_trusted(self):
        run = mock.Mock(return_value=subprocess.CompletedProcess([], 0, "Success.", ""))
        dl = workshop.Downloads(games.CK3, run)
        self.assertEqual(self.wait(dl, dl.start(str(self.exe), "acct", ["9"])["id"])["items"]["9"]["state"], "failed")

    def test_only_one_job_at_a_time(self):
        gate = []

        def slow(argv, **kw):
            while not gate:
                time.sleep(0.01)
            return subprocess.CompletedProcess(argv, 1, "", "")
        dl = workshop.Downloads(games.CK3, slow)
        first = dl.start(str(self.exe), "acct", ["1"])
        with self.assertRaises(ValueError):
            dl.start(str(self.exe), "acct", ["2"])
        gate.append(1)
        self.wait(dl, first["id"])
        dl.start(str(self.exe), "acct", ["2"])  # fine once the first has finished
        self.assertNotIn("thread", dl.status()[0])


class PresetApi(GameCase):
    GAME = games.CK3

    def test_list_and_apply_creates_a_playset_with_missing_workshop_mods(self):
        self.req("GET", "/api/state")  # the game is scanned on first use; add the mod afterwards
        mkworkshop(self.ws(), 2273832430, "RICE")
        s, lst, _ = self.req("GET", "/api/presets")
        rice = [p for p in lst if p["id"] == "ck3-rice-stack"][0]
        self.assertEqual((s, rice["installed"], rice["total"], rice["status"]), (200, 0, 4, "unverified"))
        self.post("/api/rescan")
        rice = [p for p in self.req("GET", "/api/presets")[1] if p["id"] == "ck3-rice-stack"][0]
        self.assertEqual(rice["installed"], 1)
        s, res, _ = self.post("/api/presets/ck3-rice-stack/apply")
        self.assertEqual((s, res["status"], len(res["missing"])), (200, "unverified", 3))
        ps = [p for p in self.req("GET", "/api/state")[1]["playsets"] if p["id"] == res["id"]][0]
        self.assertEqual(sorted(ps["mods"]), sorted(f"ws:{m}" for m in ("2273832430", "2507209632", "2227658180", "2243307127")))
        an = self.req("GET", f"/api/analyse/{res['id']}")[1]
        self.assertEqual(sum(i["code"] == "missing_module" for i in an["issues"]), 3)  # clearly "not installed", not silent

    def test_unknown_preset_and_other_games_presets(self):
        self.assertEqual(self.post("/api/presets/nope/apply")[0], 404)
        self.assertEqual(self.post("/api/presets/ck3-rice-stack/apply", game=games.EU5)[0], 404)

    def test_open_in_steam_uses_the_opener_and_validates_ids(self):
        s, r, _ = self.post("/api/downloads", {"ids": ["111", 222], "method": "steam"})
        self.assertEqual((s, r["opened"]), (200, ["steam://url/CommunityFilePage/111", "steam://url/CommunityFilePage/222"]))
        self.assertEqual(self.opened, r["opened"])
        for body in ({"ids": ["x"], "method": "steam"}, {"ids": [], "method": "steam"}, {"ids": ["1"], "method": "rm"},
                     {"method": "steam"}, {"ids": "1", "method": "steam"}):
            self.assertEqual(self.post("/api/downloads", body)[0], 400, body)
        self.assertEqual(len(self.opened), 2)

    def test_steamcmd_download_needs_setup_then_runs_and_reports(self):
        self.assertEqual(self.post("/api/downloads", {"ids": ["1"], "method": "steamcmd"})[0], 400)
        exe = self.r / "sc" / "steamcmd.sh"
        exe.parent.mkdir()
        exe.write_text("#!/bin/sh\n")
        app = self.hub.app("ck3")
        content = workshop.content_dir(exe, games.CK3)
        app.downloads = workshop.Downloads(games.CK3, FakeRun(content))
        st, state, _ = self.post("/api/paths", {"steamcmd": str(exe), "steam_user": "acct"})
        self.assertEqual((st, state["steam_user"]), (200, "acct"))
        s, r, _ = self.post("/api/downloads", {"ids": ["333"], "method": "steamcmd"})
        self.assertEqual((s, r["method"]), (200, "steamcmd"))
        for _ in range(200):
            jobs = self.req("GET", "/api/downloads")[1]
            if jobs and jobs[0]["state"] != "running" and jobs[0]["state"] != "queued":
                break
            time.sleep(0.02)
        self.assertEqual(jobs[0]["state"], "done")
        self.assertEqual(Path(jobs[0]["dir"]), content)

    def test_presets_endpoints_are_protected_like_the_rest(self):
        self.assertEqual(self.post("/api/downloads", {"ids": ["1"], "method": "steam"}, headers={"Origin": "http://evil.example"})[0], 403)
        self.assertEqual(self.post("/api/presets/ck3-rice-stack/apply", headers={"Host": "evil.example"})[0], 403)
        self.assertEqual(self.opened, [])

    def test_save_playset_as_preset_then_apply_it_elsewhere(self):
        mkworkshop(self.ws(), 555, "Five")
        self.post("/api/rescan")
        pid = self.new_playset(["ws:555", "ws:666"])
        s, p, _ = self.post(f"/api/playsets/{pid}/save-preset", {"id": "my-five", "name": "My five"})
        self.assertEqual((s, p["id"]), (200, "my-five"))
        self.assertEqual(self.post(f"/api/playsets/{pid}/save-preset", {"id": "../x", "name": "x"})[0], 400)
        res = self.post("/api/presets/my-five/apply")[1]
        self.assertEqual([m["workshop_id"] for m in res["missing"]], ["666"])
        loc = self.new_playset(["local:nothing-shareable"])
        self.assertEqual(self.post(f"/api/playsets/{loc}/save-preset", {"id": "empty", "name": "e"})[0], 400)


if __name__ == "__main__":
    unittest.main()
