"""Games the user adds in the app (beta): the form is checked, the game works like a built-in one, and the list is kept."""
import json
from pathlib import Path

from modmanager import customgames, games
from tests.helpers import GameCase, mkmod

STELLARIS = {"name": "Stellaris", "kind": "paradox", "app_id": "281990", "user_dir_name": "Stellaris",
             "install_dir_name": "Stellaris", "install_marker": "common", "content_dir": "", "load_file": "dlc_load.json",
             "load_style": "descriptor", "def_dirs": "common, events", "accent": "#5fa8d3"}


class Validation(GameCase):
    def bad(self, **over):
        with self.assertRaises(ValueError):
            customgames.clean({**STELLARIS, **over})

    def test_a_good_definition_is_normalised(self):
        c = customgames.clean(STELLARIS)
        self.assertEqual(c["content_dir"], "")
        self.assertEqual(c["install_marker"], "common")
        self.assertEqual(c["def_dirs"], "common, events")

    def test_folder_names_cannot_climb_out(self):
        for field in ("install_marker", "content_dir"):
            for evil in ("../x", "a/../b", "C:\\Windows", "a\\..\\b"):
                self.bad(**{field: evil})
        self.bad(user_dir_name="../x")
        self.bad(install_dir_name="a/b")
        self.bad(user_parent="..")
        self.bad(load_file="../dlc_load.json")
        self.bad(def_dirs="common, ../x")

    def test_other_fields(self):
        self.bad(name="  ")
        self.bad(name="x" * 41)
        self.bad(kind="exe")
        self.bad(app_id="12ab")
        self.bad(accent="red")
        self.bad(load_style="magic")
        with self.assertRaises(ValueError):
            customgames.clean("not a dict")

    def test_modules_kind_needs_a_plain_executable_path(self):
        d = {"name": "M", "kind": "modules", "install_marker": "Modules/Native", "exe_rel": "bin/Game.exe", "launch_prefix": "/singleplayer -x"}
        c = customgames.clean(d)
        self.assertEqual(c["launch_prefix"], "/singleplayer -x")
        self.assertEqual(customgames.clean(c)["launch_prefix"], "/singleplayer -x")   # a saved one can be saved again
        with self.assertRaises(ValueError):
            customgames.clean({**d, "exe_rel": "../Game.exe"})
        with self.assertRaises(ValueError):
            customgames.clean({**d, "launch_prefix": "; rm -rf"})

    def test_every_template_is_valid(self):
        for t in customgames.TEMPLATES:
            c = customgames.clean({"name": t.get("name", "Some game"), **{k: v for k, v in t.items() if k not in ("key", "label")}})
            customgames.to_game("cg-x", c)

    def test_theme_has_every_colour_the_page_uses(self):
        built_in = set(games.CK3.theme)
        self.assertTrue(built_in <= set(customgames.theme_from("#5fa8d3")))
        for acc in ("#000000", "#ffffff", "#ffd400"):
            for v in customgames.theme_from(acc).values():
                self.assertRegex(v, r"^#[0-9a-f]{6}$")


class Persistence(GameCase):
    def test_saved_list_survives_a_restart_and_bad_entries_are_skipped(self):
        path = self.r / "c.json"
        c = customgames.CustomGames(path)
        gid, g = c.save(STELLARIS)
        self.assertTrue(gid.startswith("cg-stellaris"))
        self.assertTrue(g.custom and not g.verified)
        doc = json.loads(path.read_text(encoding="utf-8"))
        doc["games"].append({"id": "cg-evil", "name": "x", "install_marker": "../.."})
        doc["games"].append({"id": "ck3", "name": "Not mine"})
        doc["games"].append("junk")
        path.write_text(json.dumps(doc), encoding="utf-8")
        again = customgames.CustomGames(path)
        self.assertEqual(list(again.defs), [gid])

    def test_same_name_gets_a_new_id_and_the_list_has_a_limit(self):
        c = customgames.CustomGames()
        ids = {c.save(STELLARIS)[0] for _ in range(3)}
        self.assertEqual(len(ids), 3)
        for _ in range(customgames.MAX_GAMES - 3):
            c.save(STELLARIS)
        with self.assertRaises(ValueError):
            c.save(STELLARIS)


class AddedGameWorks(GameCase):
    GAME = games.CK3

    def add(self, d=None, gid=None):
        st, r, _ = self.post("/api/custom-games", {"game": d or STELLARIS, **({"id": gid} if gid else {})})
        self.assertEqual(st, 200, r)
        return r["id"]

    def test_add_edit_remove(self):
        gid = self.add()
        st, idx, _ = self.req("GET", "/api/games")
        mine = [g for g in idx["games"] if g["id"] == gid]
        self.assertEqual(len(mine), 1)
        self.assertTrue(mine[0]["custom"])
        self.assertEqual(idx["custom_games"][gid]["name"], "Stellaris")
        self.assertTrue(len(idx["game_templates"]) >= 3)
        self.assertEqual(self.addgames(idx), {"ck3", "eu5", "vic3", "bannerlord", gid})
        # edit
        self.add({**STELLARIS, "name": "Stellaris 2"}, gid)
        self.assertEqual(self.req("GET", "/api/games")[1]["custom_games"][gid]["name"], "Stellaris 2")
        # a built-in cannot be changed or removed
        self.assertEqual(self.post("/api/custom-games", {"id": "ck3", "game": STELLARIS})[0], 400)
        self.assertEqual(self.post("/api/custom-games/remove", {"id": "ck3"})[0], 400)
        self.assertEqual(self.post("/api/custom-games", {"game": {**STELLARIS, "install_marker": "../.."}})[0], 400)
        # remove: gone from the list, its folder in the config dir stays unless asked
        (self.r / "cfg" / gid).mkdir(parents=True, exist_ok=True)
        self.assertEqual(self.post("/api/custom-games/remove", {"id": gid})[0], 200)
        self.assertNotIn(gid, self.addgames(self.req("GET", "/api/games")[1]))
        self.assertTrue((self.r / "cfg" / gid).is_dir())
        self.assertEqual(self.req("GET", f"/api/{gid}/state")[0], 404)

    def addgames(self, idx):
        return {g["id"] for g in idx["games"]}

    def test_remove_can_erase_its_data(self):
        gid = self.add()
        (self.r / "cfg" / gid).mkdir(parents=True, exist_ok=True)
        (self.r / "cfg" / gid / "playsets.json").write_text("{}", encoding="utf-8")
        self.post("/api/custom-games/remove", {"id": gid, "erase_data": True})
        self.assertFalse((self.r / "cfg" / gid).exists())

    def test_an_added_game_behaves_like_a_built_in_one(self):
        gid = self.add()
        g = self.hub.games[gid]
        self.assertEqual(g.vanilla_dir_name, "")          # base content sits straight under the install root
        user = self.user(g)
        mkmod(user, "m1", "First")
        mkmod(user, "m2", "Second", deps=["First"])
        self.post(f"/api/{gid}/rescan")
        st, state, _ = self.req("GET", f"/api/{gid}/state")
        self.assertEqual(st, 200)
        self.assertEqual({m["name"] for m in state["mods"]}, {"First", "Second"})
        self.assertTrue(state["game"]["custom"])
        pid = self.post("/api/playsets", {"name": "P", "mods": ["local:m2", "local:m1"]}, game=g)[1]["id"]
        self.post(f"/api/{gid}/playsets/{pid}/autosort", {})
        order = self.req("GET", f"/api/{gid}/state")[1]["playsets"][0]["mods"]
        self.assertEqual(order, ["local:m1", "local:m2"])    # dependency order, as for the built-in games

    def test_install_is_found_by_the_chosen_marker(self):
        gid = self.add()
        g = self.hub.games[gid]
        root = self.r / "lib/steamapps/common/Stellaris"
        (root / "common").mkdir(parents=True)
        from modmanager import detect
        self.assertEqual(detect.find_install_root(root / "common" / "x", g), root)
        self.assertIsNone(detect.find_install_root(self.r, g))

    def test_diagnose_lists_what_is_missing_and_what_is_found(self):
        gid = self.add()
        g = self.hub.games[gid]
        mkmod(self.user(g), "m1", "First")
        self.post(f"/api/{gid}/rescan")
        st, rep, _ = self.req("GET", f"/api/{gid}/diagnose")
        self.assertEqual(st, 200)
        by = {c["label"]: c for c in rep["checks"]}
        self.assertFalse(by["Game install"]["ok"])
        self.assertIn("common", by["Game install"]["detail"])    # says what it was looking for
        self.assertTrue(by["User folder"]["ok"])
        self.assertTrue(by["Mods found"]["ok"])
        self.assertIn("1 local", by["Mods found"]["detail"])
        self.assertTrue(rep["beta"])
        # works for a built-in game too
        self.assertEqual(self.req("GET", "/api/ck3/diagnose")[0], 200)

    def test_erase_all_removes_added_games(self):
        gid = self.add()
        self.post("/api/erase-all", {"confirm": "ERASE"})
        self.assertNotIn(gid, self.addgames(self.req("GET", "/api/games")[1]))
        self.assertFalse((self.r / "cfg" / "custom_games.json").exists())

    def test_added_games_come_back_after_a_restart(self):
        gid = self.add()
        from modmanager.server import Hub
        again = Hub()
        self.assertIn(gid, again.games)
        self.assertTrue(again.games[gid].custom)
