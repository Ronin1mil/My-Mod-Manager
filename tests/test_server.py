"""HTTP-level tests against a real server instance on an ephemeral port."""
import http.client
import json
import os
import tempfile
import threading
import unittest
import zipfile
from unittest import mock
from http.server import ThreadingHTTPServer
from pathlib import Path

from modmanager.library import Library
from modmanager import games
from modmanager.server import GameApp, Hub, make_handler
from modmanager.store import GlobalSettings, Store


def mkmod(root, folder, name, deps=(), files=None):
    d = Path(root) / "mod" / folder
    (d / ".metadata").mkdir(parents=True, exist_ok=True)
    (d / ".metadata/metadata.json").write_text(json.dumps({
        "name": name, "version": "1", "relationships": [{"rel_type": "dependency", "display_name": x} for x in deps]}))
    for rel, txt in (files or {}).items():
        (d / rel).parent.mkdir(parents=True, exist_ok=True)
        (d / rel).write_text(txt)
    (Path(root) / "mod" / f"{folder}.mod").write_text(f'name="{name}"\npath="mod/{folder}"\n')


APP_WIDE = ("/api/settings", "/api/update-check", "/api/games", "/api/full-rescan")


class Base(unittest.TestCase):
    GAME = games.VIC3

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.r = Path(self.tmp.name)
        _p = mock.patch.dict(os.environ, {"MODMANAGER_CONFIG_DIR": str(self.r / "cfg")})
        _p.start()
        self.addCleanup(_p.stop)
        for f, n, d in (("lib", "Lib", []), ("a", "A", ["Lib"]), ("b", "B", ["A"]), ("c", "C", [])):
            mkmod(self.r / "user", f, n, d)
        self.app = GameApp(self.GAME, user_dir=self.r / "user", workshop_dir=self.r / "none", game_version_="1.7.6",
                           store=Store(self.r / "p.json"), library=Library(self.r / "l.json"), autodetect=False)
        self.hub = Hub.single(self.app, settings=GlobalSettings(self.r / "g.json"))
        self.srv = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(self.hub))
        self.port = self.srv.server_address[1]
        threading.Thread(target=lambda: self.srv.serve_forever(poll_interval=0.01), daemon=True).start()

    def tearDown(self):
        self.srv.shutdown()
        self.srv.server_close()
        self.tmp.cleanup()

    def scoped(self, path):
        """Game-scoped API paths get the game id inserted: /api/state -> /api/vic3/state."""
        if path.startswith("/api/") and not path.startswith(APP_WIDE):
            return f"/api/{self.GAME.id}/" + path[5:]
        return path

    def req(self, method, path, body=None, headers=None, raw=None):
        path = self.scoped(path)
        c = http.client.HTTPConnection("127.0.0.1", self.port, timeout=10)
        h = dict(headers or {})
        data = raw
        if body is not None:
            data = json.dumps(body).encode()
            h.setdefault("Content-Type", "application/json")
        c.request(method, path, data, h)
        r = c.getresponse()
        txt = r.read()
        c.close()
        try:
            return r.status, json.loads(txt), r
        except ValueError:
            return r.status, txt, r

    def post(self, path, body=None, **kw):
        return self.req("POST", path, {} if body is None else body, **kw)

    def new_playset(self, mods=None):
        return self.post("/api/playsets", {"name": "T", "mods": mods or []})[1]["id"]


class LoadOrder(Base):
    def test_adding_mods_in_bad_order_autosorts(self):
        pid = self.new_playset()
        st, ps, _ = self.post(f"/api/playsets/{pid}/update", {"mods": ["local:b", "local:c", "local:a", "local:lib"]})
        self.assertEqual(st, 200)
        self.assertEqual(sorted(ps["mods"]), ["local:a", "local:b", "local:c", "local:lib"])
        pos = {m: i for i, m in enumerate(ps["mods"])}
        self.assertLess(pos["local:lib"], pos["local:a"])
        self.assertLess(pos["local:a"], pos["local:b"])
        an = self.req("GET", f"/api/analyse/{pid}")[1]
        self.assertEqual(an["issues"], [])

    def test_manual_mode_keeps_order_and_reports_then_fix_sorts(self):
        pid = self.new_playset()
        self.post(f"/api/playsets/{pid}/update", {"auto_sort": False})
        bad = ["local:b", "local:a", "local:lib"]
        ps = self.post(f"/api/playsets/{pid}/update", {"mods": bad})[1]
        self.assertEqual(ps["mods"], bad)
        an = self.req("GET", f"/api/analyse/{pid}")[1]
        self.assertEqual({i["code"] for i in an["issues"]}, {"wrong_order"})
        self.assertTrue(all(i["fix"] == {"kind": "autosort"} for i in an["issues"]))
        ps = self.post(f"/api/playsets/{pid}/autosort")[1]
        self.assertEqual(ps["mods"], ["local:lib", "local:a", "local:b"])
        self.assertEqual(self.req("GET", f"/api/analyse/{pid}")[1]["issues"], [])

    def test_enable_fix_pulls_transitive_dependencies_in_front(self):
        pid = self.new_playset(["local:c"])
        st, ps, _ = self.post(f"/api/playsets/{pid}/enable", {"id": "local:b"})
        self.assertEqual(st, 200)
        self.assertEqual(sorted(ps["mods"]), ["local:a", "local:b", "local:c", "local:lib"])
        pos = {m: i for i, m in enumerate(ps["mods"])}
        self.assertLess(pos["local:lib"], pos["local:a"])
        self.assertLess(pos["local:a"], pos["local:b"])
        self.assertEqual(self.req("GET", f"/api/analyse/{pid}")[1]["issues"], [])

    def test_enable_fix_reenables_a_disabled_dependency(self):
        pid = self.new_playset()
        self.post(f"/api/playsets/{pid}/update", {"mods": ["local:lib", "local:a"], "disabled": ["local:lib"]})
        an = self.req("GET", f"/api/analyse/{pid}")[1]
        fix = [i["fix"] for i in an["issues"] if i["code"] == "disabled_dependency"][0]
        ps = self.post(f"/api/playsets/{pid}/enable", {"id": fix["id"]})[1]
        self.assertEqual(ps["disabled"], [])
        self.assertEqual(self.req("GET", f"/api/analyse/{pid}")[1]["issues"], [])

    def test_disabling_and_reenabling_keeps_a_valid_order(self):
        pid = self.new_playset()
        self.post(f"/api/playsets/{pid}/update", {"mods": ["local:lib", "local:a", "local:b"]})
        ps = self.post(f"/api/playsets/{pid}/update", {"disabled": ["local:a"]})[1]
        self.assertEqual(ps["mods"], ["local:lib", "local:a", "local:b"])  # disabled keeps its slot
        ps = self.post(f"/api/playsets/{pid}/update", {"disabled": []})[1]
        self.assertEqual(ps["mods"], ["local:lib", "local:a", "local:b"])

    def test_launch_writes_exactly_the_enabled_order(self):
        pid = self.new_playset()
        self.post(f"/api/playsets/{pid}/update", {"mods": ["local:b", "local:c", "local:a", "local:lib"],
                                                   "disabled": ["local:c"]})
        self.app.game_exe = None
        import webbrowser
        opened = []
        with mock.patch.object(webbrowser, "open", lambda url: opened.append(url) or True):
            st, res, _ = self.post(f"/api/playsets/{pid}/launch")
        self.assertEqual((st, res["written"], res["via"]), (200, 3, "steam"))
        cl = json.loads((self.r / "user/content_load.json").read_text())
        self.assertEqual([Path(e["path"]).name for e in cl["enabledMods"]], ["lib", "a", "b"])
        self.assertEqual(opened, ["steam://run/529340"])

    def test_duplicate_playset_is_independent(self):
        pid = self.new_playset(["local:lib"])
        did = self.post(f"/api/playsets/{pid}/duplicate", {"name": "Copy"})[1]["id"]
        self.post(f"/api/playsets/{did}/update", {"mods": ["local:c"]})
        state = self.req("GET", "/api/state")[1]
        by = {p["id"]: p for p in state["playsets"]}
        self.assertEqual((by[pid]["mods"], by[did]["mods"]), (["local:lib"], ["local:c"]))

    def test_conflict_winner_follows_load_order(self):
        mkmod(self.r / "user", "x", "X", files={"common/goods/g.txt": "k = {}"})
        mkmod(self.r / "user", "y", "Y", files={"common/goods/g.txt": "k = {}"})
        self.post("/api/rescan")
        pid = self.new_playset()
        self.post(f"/api/playsets/{pid}/update", {"auto_sort": False})
        self.post(f"/api/playsets/{pid}/update", {"mods": ["local:x", "local:y"]})
        c = self.req("GET", f"/api/analyse/{pid}")[1]["conflicts"]
        self.assertEqual({x["winner"] for x in c}, {"local:y"})
        self.post(f"/api/playsets/{pid}/update", {"mods": ["local:y", "local:x"]})
        c = self.req("GET", f"/api/analyse/{pid}")[1]["conflicts"]
        self.assertEqual({x["winner"] for x in c}, {"local:x"})
        self.post(f"/api/playsets/{pid}/update", {"disabled": ["local:x"]})
        self.assertEqual(self.req("GET", f"/api/analyse/{pid}")[1]["conflicts"], [])


class RescanFindsSteamcmd(Base):
    def test_a_pressed_rescan_looks_for_steamcmd_but_window_focus_does_not(self):
        exe = self.r / "sc" / "steamcmd.exe"
        exe.parent.mkdir()
        exe.write_text("")
        with mock.patch("modmanager.workshop.find_steamcmd", return_value=exe) as find:
            st = self.post("/api/rescan", {"light": True})[1]
            self.assertIsNone(st["steamcmd_found"])
            find.assert_not_called()
            st = self.post("/api/rescan")[1]
        self.assertEqual(st["steamcmd_found"]["steamcmd"], str(exe))
        self.assertEqual(st["steamcmd"], str(exe))


class FullRescanRoute(Base):
    def test_rescan_button_route_reads_new_mods_of_the_games_used(self):
        self.hub.settings.update(last_game=self.GAME.id)
        mkmod(self.r / "user", "d", "D")
        with mock.patch("modmanager.detect.detect_all", return_value=[]):
            st, r, _ = self.post("/api/full-rescan")
        self.assertEqual(st, 200, r)
        g = r["games"][0]
        self.assertEqual((g["id"], g["mods"], g["added"]), (self.GAME.id, 5, 1))
        self.assertIn("local:d", {m["id"] for m in self.req("GET", "/api/state")[1]["mods"]})
        self.assertEqual(self.req("POST", "/api/full-rescan", {}, headers={"Origin": "http://evil.example"})[0], 403)


class SteamRateLimit(Base):
    def test_the_page_gets_a_429_with_the_seconds_to_count_down(self):
        from modmanager import collections

        def limited(path, fields):
            raise collections.RateLimited(90)
        self.srv.collection_post = limited
        st, body, _ = self.post("/api/presets/import-collection", {"url": "123"})
        self.assertEqual(st, 429)
        self.assertEqual((body["retry_in"], body["rate_limit"]), (90, "steam"))
        self.assertIn("1:30", body["error"])


class Hardening(Base):
    def test_bad_host_and_origin_are_refused(self):
        self.assertEqual(self.req("GET", "/api/state", headers={"Host": "evil.example"})[0], 403)
        self.assertEqual(self.req("POST", "/api/rescan", {}, headers={"Host": "127.0.0.1.evil.example"})[0], 403)
        st = self.req("POST", "/api/playsets", {"name": "x"}, headers={"Origin": "http://evil.example"})[0]
        self.assertEqual(st, 403)
        self.assertEqual(self.req("POST", "/api/playsets", {"name": "x"},
                                  headers={"Origin": f"http://127.0.0.1:{self.port}"})[0], 200)

    def test_invalid_input_gets_400_not_500_and_changes_nothing(self):
        pid = self.new_playset(["local:lib"])
        before = self.req("GET", "/api/state")[1]["playsets"]
        for body in ({"name": ""}, {"name": "x" * 61}, {"mods": "nope"}, {"mods": [1]}, {"notes": "n" * 2001},
                     {"launch_args": ["; calc"]}, {"launch_args": "x"}, {"auto_sort": "yes"},
                     {"disabled": {"a": 1}}):
            st, res, _ = self.post(f"/api/playsets/{pid}/update", body)
            self.assertEqual(st, 400, body)
            self.assertIn("error", res)
        self.assertEqual(self.req("GET", "/api/state")[1]["playsets"], before)

    def test_unknown_ids_and_paths(self):
        self.assertEqual(self.req("GET", "/api/analyse/nope")[0], 404)
        self.assertEqual(self.post("/api/playsets/nope/update", {"name": "x"})[0], 404)
        self.assertEqual(self.post("/api/playsets/nope/launch")[0], 404)
        pid = self.new_playset()
        self.assertEqual(self.post(f"/api/playsets/{pid}/enable", {"id": "local:ghost"})[0], 400)
        self.assertEqual(self.post("/api/mods/local%3Aghost/uninstall")[0], 400)
        for p in ("/../../etc/passwd", "/static/../app.js", "/%2e%2e/%2e%2e/etc/passwd", "/app.js/../x", "/nope"):
            self.assertEqual(self.req("GET", p)[0], 404, p)

    def test_malformed_json_and_oversize_bodies(self):
        st, _, _ = self.req("POST", "/api/playsets", raw=b"{not json", headers={"Content-Type": "application/json"})
        self.assertIn(st, (400, 500))
        self.assertLess(st, 600)
        # the cap is enforced from the Content-Length header alone, before any body is read
        for path, size in (("/api/vic3/import", 1024 * 1024 + 1), ("/api/vic3/install", 1024**3 + 1)):
            c = http.client.HTTPConnection("127.0.0.1", self.port, timeout=10)
            c.putrequest("POST", path)
            c.putheader("Content-Length", str(size))
            c.endheaders()
            r = c.getresponse()
            self.assertEqual(r.status, 413, path)
            c.close()
        c = http.client.HTTPConnection("127.0.0.1", self.port, timeout=10)
        c.putrequest("POST", "/api/vic3/import")
        c.putheader("Content-Length", "-5")
        c.endheaders()
        self.assertEqual(c.getresponse().status, 413)
        c.close()
        self.assertEqual(self.req("GET", "/api/state")[0], 200)  # server still alive

    def test_security_headers_and_static_allowlist(self):
        st, body, r = self.req("GET", "/")
        self.assertEqual(st, 200)
        self.assertIn("script-src 'self'", r.getheader("Content-Security-Policy"))
        self.assertEqual(r.getheader("X-Content-Type-Options"), "nosniff")
        self.assertEqual(r.getheader("X-Frame-Options"), "DENY")
        for name in ("app.js", "style.css", "index.html"):
            self.assertEqual(self.req("GET", "/" + name)[0], 200)
        self.assertNotIn(b"<script>", body.replace(b'<script src="/app.js"></script>', b""))  # no inline script

    def test_import_export_roundtrip_over_http(self):
        pid = self.new_playset(["local:lib", "local:a"])
        self.post(f"/api/playsets/{pid}/update", {"notes": "hello", "launch_args": ["-debug_mode"]})
        shared = self.req("GET", f"/api/playsets/{pid}/share")[1]
        st, res, _ = self.post("/api/import", shared)
        self.assertEqual((st, res["missing"]), (200, []))
        ps = [p for p in self.req("GET", "/api/state")[1]["playsets"] if p["id"] == res["id"]][0]
        self.assertEqual((ps["mods"], ps["notes"], ps["launch_args"]), (["local:lib", "local:a"], "hello", ["-debug_mode"]))
        shared["mods"].append({"name": "Not Installed", "remote_id": "999"})
        self.assertEqual(self.post("/api/import", shared)[1]["missing"], ["Not Installed"])
        self.assertEqual(self.post("/api/import", {"format": "other"})[0], 400)

    def test_install_and_uninstall_over_http(self):
        z = self.r / "n.zip"
        with zipfile.ZipFile(z, "w") as zf:
            zf.writestr("N/.metadata/metadata.json", json.dumps({"name": "New"}))
        st, res, _ = self.req("POST", "/api/install", raw=z.read_bytes(), headers={"X-Filename": "../../n.zip"})
        self.assertEqual((st, res["installed"][0]["id"]), (200, "local:N"))
        self.assertTrue((self.r / "user/mod/N").is_dir())
        self.assertEqual(self.post("/api/mods/local%3AN/uninstall")[0], 200)
        self.assertFalse((self.r / "user/mod/N").exists())
        # bad archive: clear error, nothing left in staging
        st, res, _ = self.req("POST", "/api/install", raw=b"junk", headers={"X-Filename": "x.zip"})
        self.assertEqual(st, 400)
        self.assertEqual(list((self.r / "cfg/vic3/staging").iterdir()), [])


class Concurrency(Base):
    def test_parallel_requests_never_corrupt_state(self):
        pid = self.new_playset()
        errors = []

        def worker(k):
            try:
                for j in range(15):
                    mods = ["local:lib", "local:a", "local:b", "local:c"][: 1 + (k + j) % 4]
                    st = self.post(f"/api/playsets/{pid}/update", {"mods": mods, "notes": f"w{k}-{j}"})[0]
                    st2 = self.post("/api/rescan")[0]
                    st3 = self.req("GET", f"/api/analyse/{pid}")[0]
                    if (st, st2, st3) != (200, 200, 200):
                        errors.append((k, j, st, st2, st3))
            except Exception as e:  # noqa: BLE001
                errors.append(repr(e))

        ts = [threading.Thread(target=worker, args=(k,)) for k in range(8)]
        [t.start() for t in ts]
        [t.join() for t in ts]
        self.assertEqual(errors, [])
        # the file on disk is valid JSON and a fresh Store can load it
        data = json.loads((self.r / "p.json").read_text())
        self.assertIn(pid, data["playsets"])
        self.assertIsInstance(Store(self.r / "p.json").get(pid)["mods"], list)
        self.assertTrue(json.loads((self.r / "l.json").read_text())["entries"])


def fake_github(tag="v9.0.0", counter=None, delay=0.0):
    import time

    def fetch(url):
        if counter is not None:
            counter.append(url)
        time.sleep(delay)
        if url.endswith("/releases/latest"):
            return 200, {"tag_name": tag, "html_url": "https://github.com/Ronin1mil/My-Mod-Manager/releases/tag/" + tag,
                         "body": "Big update", "assets": [], "published_at": "2026-11-01T00:00:00Z"}
        return 404, None
    return fetch


def fake_both(release_tag="v0.9.1", build="def5678", counter=None):
    base = "https://github.com/Ronin1mil/My-Mod-Manager/releases/"
    rel = fake_github(release_tag, counter)

    def fetch(url):
        if url.endswith("/releases/tags/test-build"):
            if counter is not None:
                counter.append(url)
            return 200, {"body": f"Test build.\n\nbuild: {build}\n", "published_at": "2026-10-30T01:00:00Z", "prerelease": True,
                         "assets": [{"id": 1, "name": "Mod-Manager-python.pyzw", "size": 3, "browser_download_url": base + "download/test-build/Mod-Manager-python.pyzw"}]}
        return rel(url)
    return fetch


class Updates(Base):
    def test_a_test_build_is_offered_newer_test_builds_before_any_release(self):
        from unittest import mock
        from modmanager import __version__
        self.hub.update_fetch = fake_both(release_tag="v" + __version__)   # the release of its own version is out
        with mock.patch("modmanager.server.BUILD", "abc1234"):
            r = self.hub.check_update(True)
        self.assertEqual((r["build"], r["update_available"]), ("def5678", True))
        with mock.patch("modmanager.server.BUILD", "def5678"):   # on the newest build: nothing to offer, not the release either
            r = self.hub.check_update(True)
        self.assertEqual((r["status"], r["update_available"]), ("current", False))

    def test_a_normal_copy_only_follows_releases(self):
        from unittest import mock
        self.hub.update_fetch = fake_both(release_tag="v9.0.0")
        with mock.patch("modmanager.server.BUILD", ""), mock.patch("modmanager.update.BUILD", ""):
            r = self.hub.check_update(True)
        self.assertEqual((r["latest"], r.get("build")), ("9.0.0", None))


    def test_auto_check_is_off_by_default_and_makes_no_request(self):
        calls = []
        self.hub.update_fetch = fake_github(counter=calls)
        self.assertEqual(self.req("GET", "/api/games")[1]["settings"]["auto_update_check"], False)
        self.assertIsNone(self.hub.check_on_launch())  # what serve() calls at start-up
        self.assertEqual(calls, [])
        self.assertIsNone(self.req("GET", "/api/games")[1]["update"])

    def test_enabling_the_setting_persists_and_checks_on_next_launch(self):
        calls = []
        st, res, _ = self.post("/api/settings", {"auto_update_check": True})
        self.assertEqual((st, res["auto_update_check"]), (200, True))
        # survives a restart: a fresh Store reads it back
        self.assertTrue(GlobalSettings(self.r / "g.json").get()["auto_update_check"])
        self.hub.update_fetch = fake_github("v9.0.0", calls)
        t = self.hub.check_on_launch()
        self.assertIsNotNone(t)
        t.join(5)
        self.assertFalse(self.hub.update_pending)
        self.assertEqual(len(calls), 1)  # releases/latest only
        s = self.req("GET", "/api/games")[1]
        self.assertEqual((s["update"]["status"], s["update"]["latest"], s["version"]), ("update", "9.0.0", s["version"]))
        self.assertTrue(s["update"]["update_available"])
        # turning it off again stops it
        self.post("/api/settings", {"auto_update_check": False})
        self.assertIsNone(self.hub.check_on_launch())

    def test_launch_check_failure_is_silent_and_not_cached(self):
        self.post("/api/settings", {"auto_update_check": True})
        self.hub.update_fetch = lambda url: (_ for _ in ()).throw(OSError("offline"))
        self.hub.check_on_launch().join(5)
        s = self.req("GET", "/api/games")[1]
        self.assertIsNone(s["update"])  # nothing to show, no error banner
        self.assertFalse(s["update_pending"])

    def test_settings_validation(self):
        for body in ({"nope": True}, {"auto_update_check": "yes"}, {"auto_update_check": 1},
                     {"dismissed_update": "x" * 41}, {"dismissed_update": 5}, {"auto_update_check": True, "bad": 1}):
            self.assertEqual(self.post("/api/settings", body)[0], 400, body)
        self.assertFalse(self.req("GET", "/api/games")[1]["settings"]["auto_update_check"])  # nothing applied
        self.assertEqual(self.post("/api/settings", {"dismissed_update": "9.0.0"})[1]["dismissed_update"], "9.0.0")

    def test_manual_check_is_cached_for_ten_minutes_unless_forced(self):
        calls = []
        self.hub.update_fetch = fake_github("v9.0.0", calls)
        self.assertEqual(self.post("/api/update-check")[1]["status"], "update")
        self.post("/api/update-check")
        self.assertEqual(len(calls), 1)
        self.post("/api/update-check", {"force": True})
        self.assertEqual(len(calls), 2)

    def test_failed_checks_are_not_cached(self):
        self.hub.update_fetch = lambda url: (_ for _ in ()).throw(OSError("offline"))
        self.assertEqual(self.post("/api/update-check")[1]["status"], "unreachable")
        calls = []
        self.hub.update_fetch = fake_github("v0.0.1", calls)
        self.assertEqual(self.post("/api/update-check")[1]["status"], "current")
        self.assertEqual(len(calls), 1)

    def test_a_slow_check_does_not_block_other_requests(self):
        import time
        self.hub.update_fetch = fake_github("v9.0.0", delay=1.5)
        t = threading.Thread(target=lambda: self.post("/api/update-check"))
        t.start()
        time.sleep(0.2)
        s = time.time()
        self.assertEqual(self.req("GET", "/api/games")[0], 200)
        self.assertLess(time.time() - s, 1.0)
        t.join()

    def test_update_check_rejects_cross_site_posts(self):
        self.assertEqual(self.post("/api/update-check", headers={"Origin": "http://evil.example"})[0], 403)
        self.assertEqual(self.post("/api/settings", {"auto_update_check": True},
                                   headers={"Origin": "http://evil.example"})[0], 403)
        self.assertFalse(self.hub.settings.get()["auto_update_check"])


class ComparePlaysets(Base):
    def test_compare_endpoint(self):
        a = self.new_playset(["local:lib", "local:a", "local:c"])
        b = self.post("/api/playsets", {"name": "B", "mods": ["local:c", "local:lib", "local:b"]})[1]["id"]
        self.post(f"/api/playsets/{b}/update", {"disabled": ["local:lib"], "auto_sort": False, "notes": "n"})
        st, r, _ = self.req("GET", f"/api/compare/{a}/{b}")
        self.assertEqual(st, 200)
        self.assertEqual(r["only_a"], ["local:a"])
        self.assertEqual(r["only_b"], ["local:b"])
        self.assertEqual(r["state"], [{"id": "local:lib", "a": "enabled", "b": "disabled"}])
        self.assertEqual({s["field"] for s in r["settings"]}, {"auto_sort", "notes"})
        self.assertEqual(r["summary"]["a"]["errors"], 0)
        self.assertGreaterEqual(r["summary"]["b"]["errors"], 1)  # B enables 'b' without its dependency chain
        self.assertEqual(self.req("GET", f"/api/compare/{a}/{a}")[1]["identical"], True)
        self.assertEqual(self.req("GET", f"/api/compare/{a}/nope")[0], 404)
        self.assertEqual(self.req("GET", f"/api/compare/nope/{a}")[0], 404)


if __name__ == "__main__":
    unittest.main()
