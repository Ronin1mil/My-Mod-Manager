"""Settings -> Erase all data (experimental): removes only what the app itself saved."""
from modmanager import games
from tests.helpers import GameCase


class EraseAll(GameCase):
    GAME = games.VIC3

    def lay_out(self):
        cfg = self.r / "cfg"
        for g in ("vic3", "ck3"):
            (cfg / g / "presets").mkdir(parents=True)
            (cfg / g / "playsets.json").write_text("{}", encoding="utf-8")
            (cfg / g / "presets" / "mine.json").write_text("{}", encoding="utf-8")
        self.post("/api/settings", {"last_game": "vic3"})  # creates the app-wide settings file
        self.assertTrue(self.hub.settings.path.is_file())
        (cfg / "window").mkdir()  # the window's own profile is left alone
        self.user().mkdir(parents=True, exist_ok=True)
        (self.user() / "content_load.json").write_text("{}", encoding="utf-8")  # the game's own file
        return cfg

    def test_without_the_confirmation_nothing_is_deleted(self):
        cfg = self.lay_out()
        for body in ({}, {"confirm": "erase"}, {"confirm": "yes"}):
            st, r, _ = self.post("/api/erase-all", body)
            self.assertEqual(st, 400, body)
        self.assertTrue((cfg / "vic3" / "playsets.json").is_file())
        self.assertTrue(self.hub.settings.path.is_file())

    def test_erasing_removes_the_apps_data_and_nothing_else(self):
        cfg = self.lay_out()
        st, r, _ = self.post("/api/erase-all", {"confirm": "ERASE"})
        self.assertEqual(st, 200)
        self.assertEqual(r["failed"], [])
        self.assertFalse((cfg / "vic3").exists())
        self.assertFalse((cfg / "ck3").exists())
        self.assertFalse(self.hub.settings.path.exists())
        self.assertTrue((cfg / "window").is_dir())
        self.assertTrue((self.user() / "content_load.json").is_file())
        self.assertEqual(self.req("GET", "/api/games")[1]["settings"]["last_game"], "")  # back to the defaults

    def test_erasing_twice_is_fine(self):
        self.lay_out()
        self.post("/api/erase-all", {"confirm": "ERASE"})
        st, r, _ = self.post("/api/erase-all", {"confirm": "ERASE"})
        self.assertEqual((st, r["erased"], r["failed"]), (200, [], []))


class UiSettings(GameCase):
    GAME = games.VIC3

    def test_scheme_and_text_size_are_saved_per_game_and_validated(self):
        st = self.req("GET", "/api/state")[1]
        self.assertEqual((st["ui_scheme"], st["ui_text"]), ("default", "normal"))
        self.assertEqual(self.post("/api/ui", {"ui_scheme": "forest", "ui_text": "xlarge"})[1]["ui_scheme"], "forest")
        self.assertEqual(self.req("GET", "/api/state")[1]["ui_text"], "xlarge")
        for bad in ({"ui_scheme": "neon"}, {"ui_text": "huge"}, {"ui_scheme": 3}):
            self.assertEqual(self.post("/api/ui", bad)[0], 400, bad)
        self.assertEqual(self.req("GET", "/api/state")[1]["ui_scheme"], "forest")  # a refused change changes nothing
        self.assertEqual(self.req("GET", "/api/ck3/state")[1]["ui_scheme"], "default")  # another game is untouched
