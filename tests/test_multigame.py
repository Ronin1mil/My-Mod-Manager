"""The same user-visible behaviour, for every game, through one running server."""
import http.client
import json
import unittest
import urllib.parse
from pathlib import Path
from unittest import mock

from modmanager import games, launch
from tests.helpers import ALL, GameCase, mkinstall, mkmod, mkworkshop


class AllGames(GameCase):
    def kw(self, g):
        kw = super().kw(g)
        mkmod(kw["user_dir"], "lib", "Lib", files={"common/traits/l.txt": "t = { }"})
        mkmod(kw["user_dir"], "a", "A", deps=["Lib"], files={"common/traits/a.txt": "t = { }"})
        mkmod(kw["user_dir"], "b", "B", deps=["A"], files={"common/traits/b.txt": "t = { }"})
        mkworkshop(kw["workshop_dir"], 123, "WS Mod", files={"common/x.txt": ""})
        return kw

    def each(self):
        for g in ALL:
            with self.subTest(game=g.id):
                yield g

    def test_games_index_lists_all_three_with_themes(self):
        s, idx, _ = self.req("GET", "/api/games")
        self.assertEqual((s, [g["id"] for g in idx["games"]]), (200, ["ck3", "eu5", "vic3", "bannerlord"]))
        self.assertTrue(all(g["theme"]["--acc"] for g in idx["games"]))
        self.assertEqual(idx["settings"]["auto_update_check"], False)

    def test_state_lists_local_and_workshop_mods_for_every_game(self):
        for g in self.each():
            st = self.req("GET", "/api/state", game=g)[1]
            self.assertEqual({m["id"] for m in st["mods"]}, {"local:lib", "local:a", "local:b", "ws:123"})
            self.assertEqual(st["game"]["id"], g.id)

    def test_load_order_autosort_and_conflict_winner_for_every_game(self):
        for g in self.each():
            pid = self.new_playset(game=g)
            ps = self.post(f"/api/playsets/{pid}/update", {"mods": ["local:b", "local:a", "local:lib"]}, game=g)[1]
            self.assertEqual(ps["mods"], ["local:lib", "local:a", "local:b"])
            an = self.req("GET", f"/api/analyse/{pid}", game=g)[1]
            self.assertEqual(an["issues"], [])
            d = [c for c in an["conflicts"] if c["kind"] == "definition"]
            self.assertEqual((d[0]["path"], d[0]["winner"]), ("common/traits: t", "local:b"))

    def test_launch_writes_the_games_own_file_and_asks_steam_for_the_games_own_app(self):
        for g in self.each():
            pid = self.new_playset(["local:lib", "ws:123", "local:a"], game=g)
            self.post(f"/api/playsets/{pid}/update", {"auto_sort": False, "mods": ["local:lib", "ws:123", "local:a"]}, game=g)
            with mock.patch.object(launch.webbrowser, "open") as op:
                s, res, _ = self.post(f"/api/playsets/{pid}/launch", game=g)
            self.assertEqual((s, res["written"], res["file"], res["via"]), (200, 3, g.load_file, "steam"))
            op.assert_called_once_with(f"steam://run/{g.app_id}")
            enabled = json.loads((self.user(g) / g.load_file).read_text())["enabled_mods"]
            if g.load_style == "descriptor":
                self.assertEqual(enabled, ["mod/lib.mod", "mod/ugc_123.mod", "mod/a.mod"])
            else:
                self.assertEqual(enabled, ["mod/lib", str(self.ws(g) / "123"), "mod/a"])
            for other in ALL:  # nothing written for the other games
                if other.id != g.id and other.load_file != g.load_file:
                    self.assertFalse((self.user(g) / other.load_file).exists())

    def test_launch_arguments_go_to_the_right_steam_url(self):
        pid = self.new_playset(["local:lib"], game=games.EU5)
        self.post(f"/api/playsets/{pid}/update", {"launch_args": ["-debug_mode"]}, game=games.EU5)
        with mock.patch.object(launch.webbrowser, "open") as op:
            self.post(f"/api/playsets/{pid}/launch", game=games.EU5)
        op.assert_called_once_with("steam://run/3450310//-debug_mode/")

    def test_games_do_not_share_playsets_libraries_or_settings(self):
        a = self.new_playset(["local:lib"], game=games.CK3)
        self.post(f"/api/playsets/{a}/update", {"notes": "ck3 only"}, game=games.CK3)
        for g in (games.EU5, games.VIC3):
            self.assertEqual(self.req("GET", "/api/state", game=g)[1]["playsets"], [])
            self.assertEqual(self.req("GET", f"/api/analyse/{a}", game=g)[0], 404)
            self.assertEqual(self.post(f"/api/playsets/{a}/launch", game=g)[0], 404)
        self.post("/api/paths", {"include_vanilla": False}, game=games.EU5)
        self.assertTrue(self.req("GET", "/api/state", game=games.CK3)[1]["include_vanilla"])
        self.assertTrue(self.hub.app("ck3").store.path != self.hub.app("eu5").store.path)

    def test_share_export_carries_the_game_and_cross_game_import_is_refused(self):
        pid = self.new_playset(["local:lib"], game=games.CK3)
        doc = self.req("GET", f"/api/playsets/{pid}/share", game=games.CK3)[1]
        self.assertEqual(doc["game"], "ck3")
        s, res, _ = self.post("/api/import", doc, game=games.CK3)
        self.assertEqual((s, res["missing"]), (200, []))
        s, res, _ = self.post("/api/import", doc, game=games.EU5)
        self.assertEqual(s, 400)
        self.assertIn("ck3", res["error"])
        self.assertEqual(self.req("GET", "/api/state", game=games.EU5)[1]["playsets"], [])

    def test_unknown_game_and_routes(self):
        for path in ("/api/hoi4/state", "/api/ck3/nope", "/api/nope", "/api/ck3", "/api/"):
            self.assertEqual(self.req("GET", path)[0], 404, path)
        self.assertEqual(self.post("/api/hoi4/playsets", {"name": "x"})[0], 404)
        self.assertEqual(self.post("/api/ck3/mods/x/nope")[0], 404)

    def test_bulk_actions_for_every_game(self):
        for g in self.each():
            pid = self.new_playset(["local:lib", "local:a", "ws:gone"], game=g)
            self.post(f"/api/playsets/{pid}/disable_all", game=g)
            self.assertEqual(self.req("GET", "/api/state", game=g)[1]["playsets"][0]["disabled"], ["local:lib", "local:a", "ws:gone"])
            self.post(f"/api/playsets/{pid}/enable_all", game=g)
            self.assertEqual(self.req("GET", "/api/state", game=g)[1]["playsets"][0]["disabled"], [])
            self.post(f"/api/playsets/{pid}/prune", game=g)
            self.assertEqual(self.req("GET", "/api/state", game=g)[1]["playsets"][0]["mods"], ["local:lib", "local:a"])

    def test_static_files_and_security_headers(self):
        for path, ctype in (("/", "text/html"), ("/app.js", "text/javascript"), ("/style.css", "text/css")):
            s, body, r = self.req("GET", path)
            self.assertEqual(s, 200, path)
            self.assertTrue(r.getheader("Content-Type").startswith(ctype))
            self.assertIn("frame-ancestors 'none'", r.getheader("Content-Security-Policy"))
            self.assertEqual(r.getheader("X-Content-Type-Options"), "nosniff")
        for p in ("/../server.py", "/%2e%2e/server.py", "/static/app.js", "/games.py"):
            self.assertEqual(self.req("GET", p)[0], 404, p)

    def test_host_and_origin_checks_cover_every_game_route(self):
        for g in self.each():
            self.assertEqual(self.req("GET", "/api/state", headers={"Host": "evil.example"}, game=g)[0], 403)
            self.assertEqual(self.post("/api/rescan", headers={"Origin": "http://evil.example"}, game=g)[0], 403)
        self.assertEqual(self.req("GET", "/api/games", headers={"Host": "127.0.0.1.evil.example"})[0], 403)

    def test_the_page_never_embeds_a_specific_games_name_or_trademarked_art(self):
        html = (Path(__file__).parent.parent / "modmanager/static/index.html").read_text()
        for word in ("Crusader", "Victoria", "Europa"):
            self.assertNotIn(word, html)
        self.assertEqual(sorted(p.name for p in (Path(__file__).parent.parent / "modmanager/static").iterdir()),
                         ["app.js", "index.html", "style.css"])  # no bundled logos


class SetupFlow(GameCase):
    GAME = games.EU5

    def kw(self, g):
        kw = super().kw(g)
        kw.pop("game_version_")
        return kw

    def test_configure_with_a_pasted_path_inside_the_install(self):
        root = mkinstall(self.r / "Lib", self.GAME, "1.0.7", files={"in_game/common/advances/a.txt": "wood = {}"})
        deep = root / "game/in_game/common/advances"
        st = self.req("GET", "/api/state")[1]
        self.assertEqual((st["game_root"], st["setup_done"]), ("", False))
        s, st, _ = self.post("/api/paths", {"game_dir": str(deep)})
        self.assertEqual((s, st["game_root"], st["game_version"], st["setup_done"]), (200, str(root), "1.0.7", True))
        self.assertEqual(self.req("GET", "/api/inspect?path=" + urllib.parse.quote(str(deep)))[1]["install"]["version"], "1.0.7")
        self.assertIsNone(self.req("GET", "/api/inspect?path=/nowhere")[1]["install"])

    def test_not_an_install_is_a_clear_400_and_changes_nothing(self):
        before = self.req("GET", "/api/state")[1]
        for body in ({"game_dir": str(self.r)}, {"user_dir": str(self.r / "missing")}, {"workshop_dir": 5},
                     {"include_vanilla": "yes"}, {"steam_user": "bad name!"}, {"steamcmd": str(self.r / "none")}):
            s, res, _ = self.post("/api/paths", body)
            self.assertEqual(s, 400, body)
        after = self.req("GET", "/api/state")[1]
        self.assertEqual((after["game_root"], after["setup_done"], after["include_vanilla"]),
                         (before["game_root"], before["setup_done"], before["include_vanilla"]))

    def test_wrong_games_install_is_rejected(self):
        root = mkinstall(self.r / "Lib", games.CK3)
        self.assertEqual(self.post("/api/paths", {"game_dir": str(root)})[0], 400)

    def test_base_game_comparison_toggle_changes_analysis(self):
        root = mkinstall(self.r / "Lib", self.GAME, files={"in_game/common/goods/base.txt": "wood = { }"})
        mkmod(self.user(), "M", files={"in_game/common/goods/m.txt": "REPLACE:wood = { }"})
        self.post("/api/paths", {"game_dir": str(root), "include_vanilla": True})
        pid = self.new_playset(["local:M"])
        an = self.req("GET", f"/api/analyse/{pid}")[1]
        self.assertEqual((an["counts"], [c.get("vanilla") for c in an["conflicts"]]), ({"vanilla": 1}, [True]))
        self.post("/api/paths", {"include_vanilla": False})
        self.assertEqual(self.req("GET", f"/api/analyse/{pid}")[1]["conflicts"], [])

    def test_skip_setup_remembers_the_choice_and_state_says_when_setup_is_needed(self):
        self.assertTrue(self.req("GET", "/api/state")[1]["setup_needed"])  # no install known yet
        self.assertTrue(self.post("/api/skip-setup")[1]["setup_done"])
        self.assertFalse(self.req("GET", "/api/state")[1]["setup_needed"])

    def test_first_boot_picks_up_an_install_automatically(self):
        from modmanager.library import Library
        from modmanager.server import GameApp
        from modmanager.store import Store
        root = mkinstall(self.r / "Lib", self.GAME, "2.0.1")
        app = GameApp(self.GAME, user_dir=self.user(), workshop_dir=self.ws(), store=Store(self.r / "x.json"),
                      library=Library(self.r / "x-lib.json"), detect_libraries=[self.r / "Lib"])
        self.assertEqual((app.first_boot, app.game_root, app.game_version), (True, root, "2.0.1"))
        self.assertEqual(Store(self.r / "x.json").settings()["game_dir"], str(root))
        again = GameApp(self.GAME, user_dir=self.user(), workshop_dir=self.ws(), store=Store(self.r / "x.json"),
                        library=Library(self.r / "x-lib.json"), autodetect=False)
        self.assertFalse(again.first_boot)  # second start uses the saved choice

    def test_workshop_folder_follows_the_install_library(self):
        from modmanager.library import Library
        from modmanager.server import GameApp
        from modmanager.store import Store
        root = mkinstall(self.r / "Lib", self.GAME)
        app = GameApp(self.GAME, user_dir=self.user(), game_dir=str(root), store=Store(self.r / "y.json"),
                      library=Library(self.r / "y-lib.json"), autodetect=False)
        self.assertEqual(app.workshop_dir, root.parent.parent / "workshop/content" / self.GAME.app_id)


class Logo(GameCase):
    GAME = games.CK3

    def test_logo_route_serves_only_a_users_own_image(self):
        self.assertEqual(self.req("GET", "/api/logo")[0], 404)
        self.assertFalse(self.req("GET", "/api/state")[1]["has_logo"])
        from modmanager.paths import config_dir
        (config_dir(games.CK3) / "logo.png").write_bytes(b"\x89PNGcustom")
        self.hub.app("ck3").apply_settings()
        s, body, r = self.req("GET", "/api/logo")
        self.assertEqual((s, body, r.getheader("Content-Type")), (200, b"\x89PNGcustom", "image/png"))


if __name__ == "__main__":
    unittest.main()
