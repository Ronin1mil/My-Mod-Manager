import json
import unittest
import urllib.error
from unittest import mock

from modmanager import update
from modmanager.update import check_for_update, is_newer, parse_version

LINK = update.LINK_PREFIX


def fake(routes):
    """routes: {url-suffix: (status, data)}; records the URLs asked for."""
    asked = []

    def fetch(url):
        asked.append(url)
        for suffix, resp in routes.items():
            if url.endswith(suffix):
                if isinstance(resp, Exception):
                    raise resp
                return resp
        return 404, None
    fetch.asked = asked
    return fetch


def release(tag, **kw):
    return {"tag_name": tag, "html_url": f"{LINK}releases/tag/{tag}", "body": "notes", "published_at": "2026-10-01T00:00:00Z",
            "assets": [{"name": "Vic3-Mod-Manager.exe", "browser_download_url": f"{LINK}releases/download/{tag}/x.exe",
                        "size": 123}], **kw}


class Versions(unittest.TestCase):
    def test_parse(self):
        self.assertEqual(parse_version("v1.2.3"), (1, 2, 3, ""))
        self.assertEqual(parse_version("1.2"), (1, 2, 0, ""))
        self.assertEqual(parse_version("1.2.3-beta.1"), (1, 2, 3, "beta.1"))
        for bad in ("", None, "latest", "v", "1", "a.b.c", "1.2.3.4.5.x!", "rolling-main"):
            self.assertIsNone(parse_version(bad), bad)

    def test_comparison(self):
        for newer, older in (("0.2.0", "0.1.9"), ("0.10.0", "0.9.0"), ("1.0.0", "0.99.99"), ("v1.0.1", "1.0.0"),
                             ("1.0.0", "1.0.0-rc.1"), ("1.0.0-rc.2", "1.0.0-rc.1"), ("1.0.0-rc.10", "1.0.0-rc.9"),
                             ("1.0.0-rc.1", "1.0.0-beta.9"), ("2.0", "1.9.9")):
            self.assertTrue(is_newer(newer, older), f"{newer} > {older}")
            self.assertFalse(is_newer(older, newer), f"{older} !> {newer}")
        self.assertFalse(is_newer("1.0.0", "1.0.0"))
        self.assertFalse(is_newer("v1.0", "1.0.0"))
        self.assertFalse(is_newer("garbage", "1.0.0"))
        self.assertFalse(is_newer("1.0.0", "garbage"))


class Check(unittest.TestCase):
    def test_update_available_from_latest_release(self):
        f = fake({"/releases/latest": (200, release("v0.2.0"))})
        r = check_for_update("0.1.0", f)
        self.assertEqual((r["status"], r["latest"], r["update_available"]), ("update", "0.2.0", True))
        self.assertEqual(r["url"], f"{LINK}releases/tag/v0.2.0")
        self.assertEqual(r["assets"][0]["name"], "Vic3-Mod-Manager.exe")
        self.assertEqual(r["notes"], "notes")
        self.assertEqual(r["published"], "2026-10-01")
        self.assertEqual(r["published_at"], "2026-10-01T00:00:00Z")   # the page shows this in the viewer's own time zone

    def test_up_to_date_and_running_ahead(self):
        f = fake({"/releases/latest": (200, release("v0.1.0"))})
        self.assertEqual(check_for_update("0.1.0", f)["status"], "current")
        self.assertFalse(check_for_update("0.3.0", f)["update_available"])  # dev build newer than release

    def test_falls_back_to_tags_when_there_is_no_release(self):
        f = fake({"/releases/latest": (404, {"message": "Not Found"}),
                  "/tags?per_page=50": (200, [{"name": "v0.2.0"}, {"name": "v0.10.0"}, {"name": "rolling"}, {"name": "v0.9.0"}])})
        r = check_for_update("0.1.0", f)
        self.assertEqual((r["status"], r["latest"]), ("update", "0.10.0"))  # numeric, not lexicographic
        self.assertTrue(r["url"].startswith(LINK))

    def test_no_releases_and_no_tags(self):
        f = fake({"/releases/latest": (404, None), "/tags?per_page=50": (200, [])})
        self.assertEqual(check_for_update("0.1.0", f)["status"], "no_releases")
        f = fake({"/releases/latest": (404, None), "/tags?per_page=50": (200, [{"name": "nightly"}])})
        self.assertEqual(check_for_update("0.1.0", f)["status"], "no_releases")

    def test_private_or_missing_repo_gives_actionable_message(self):
        r = check_for_update("0.1.0", fake({"/releases/latest": (404, None), "/tags?per_page=50": (404, None)}))
        self.assertEqual(r["status"], "unreachable")
        self.assertIn("MODMANAGER_GITHUB_TOKEN", r["message"])
        r = check_for_update("0.1.0", fake({"/releases/latest": (403, {"message": "rate limit"})}))
        self.assertEqual(r["status"], "unreachable")
        self.assertIn("rate limit", r["message"])

    def test_network_failures_never_raise(self):
        for exc in (urllib.error.URLError("dns"), TimeoutError(), ConnectionResetError(), OSError("x")):
            r = check_for_update("0.1.0", fake({"/releases/latest": exc}))
            self.assertEqual(r["status"], "unreachable", repr(exc))
        for resp in ((200, "string"), (200, [1]), (200, {"tag_name": 5}), (500, None), (200, None)):
            r = check_for_update("0.1.0", fake({"/releases/latest": resp, "/tags?per_page=50": (500, None)}))
            self.assertIn(r["status"], ("error", "no_releases", "unreachable"), resp)
            self.assertFalse(r["update_available"])
        r = check_for_update("0.1.0", fake({"/releases/latest": ValueError("too large")}))
        self.assertEqual(r["status"], "error")

    def test_hostile_response_content_is_neutralised(self):
        rel = release("v9.9.9", html_url="https://evil.example/phish", body="x" * 50000,
                      assets=[{"name": "a.exe", "browser_download_url": "https://evil.example/a.exe", "size": 1},
                              {"name": "ok.exe", "browser_download_url": f"{LINK}releases/download/v9.9.9/ok.exe", "size": "7"},
                              {"name": 5, "browser_download_url": f"{LINK}x"}, "junk", None])
        r = check_for_update("0.1.0", fake({"/releases/latest": (200, rel)}))
        self.assertEqual(r["url"], f"{LINK}releases")  # off-repo link replaced
        self.assertEqual([a["name"] for a in r["assets"]], ["ok.exe"])
        self.assertEqual(len(r["notes"]), 4000)
        # javascript:/data: links can never reach the UI either
        r = check_for_update("0.1.0", fake({"/releases/latest": (200, release("v9.9.9", html_url="javascript:alert(1)"))}))
        self.assertTrue(r["url"].startswith("https://github.com/"))

    def test_tag_names_with_odd_characters_do_not_build_odd_links(self):
        f = fake({"/releases/latest": (404, None), "/tags?per_page=50": (200, [{"name": "v2.0.0?x=1#y"}])})
        self.assertEqual(check_for_update("0.1.0", f)["status"], "no_releases")  # not a valid version at all

    def test_fetch_is_limited_to_api_github_com(self):
        for bad in ("http://api.github.com/x", "https://evil.example/x", "https://api.github.com.evil.example/x",
                    "file:///etc/passwd", "ftp://api.github.com/x"):
            with self.assertRaises(ValueError, msg=bad):
                update.default_fetch(bad)

    def test_token_is_sent_only_in_the_authorization_header_to_github(self):
        seen = {}

        class R:
            status = 200

            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

            def read(self, n):
                return json.dumps(release("v0.1.0")).encode()

        def fake_open(req, timeout=0):
            seen["url"], seen["auth"] = req.full_url, req.get_header("Authorization")
            return R()
        with mock.patch.dict("os.environ", {"MODMANAGER_GITHUB_TOKEN": "s3cret"}), \
                mock.patch("urllib.request.urlopen", fake_open):
            r = check_for_update("0.1.0")
        self.assertEqual(seen["auth"], "Bearer s3cret")
        self.assertTrue(seen["url"].startswith("https://api.github.com/repos/"))
        self.assertNotIn("s3cret", json.dumps(r))  # never echoed back to the UI
        with mock.patch.dict("os.environ", {}, clear=False) as env, mock.patch("urllib.request.urlopen", fake_open):
            env.pop("MODMANAGER_GITHUB_TOKEN", None)
            check_for_update("0.1.0")
        self.assertIsNone(seen["auth"])

    def test_oversized_response_is_rejected(self):
        class R:
            status = 200

            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

            def read(self, n):
                return b"x" * n

        with mock.patch("urllib.request.urlopen", lambda *a, **k: R()):
            with self.assertRaises(ValueError):
                update.default_fetch("https://api.github.com/x")

    def test_http_errors_are_returned_as_status_not_raised(self):
        err = urllib.error.HTTPError("https://api.github.com/x", 404, "nf", {}, None)
        err.read = lambda n=-1: b'{"message":"Not Found"}'
        with mock.patch("urllib.request.urlopen", side_effect=err):
            self.assertEqual(update.default_fetch("https://api.github.com/x"), (404, {"message": "Not Found"}))


if __name__ == "__main__":
    unittest.main()
