"""The daily Workshop mod update check (Settings > App > Tell me when Workshop mods were updated; off by default)."""
from modmanager import games
from tests.helpers import GameCase, mkworkshop

ACF = '"AppWorkshop" { "WorkshopItemsInstalled" { "111" { "timeupdated" "1000" } "222" { "timeupdated" "5000" } } }'


class DailyCheck(GameCase):
    GAME = games.CK3

    def setUp(self):
        super().setUp()
        mkworkshop(self.ws(), 111, "Old One")
        mkworkshop(self.ws(), 222, "Fresh One")
        (self.ws().parent.parent / f"appworkshop_{self.GAME.app_id}.acf").write_text(ACF)
        self.asked = []

        def steam(path, fields):
            self.asked.append(fields)
            return {"response": {"publishedfiledetails": [{"result": 1, "publishedfileid": "111", "time_updated": 2000},
                                                          {"result": 1, "publishedfileid": "222", "time_updated": 4000}]}}
        self.srv.collection_post = steam

    def test_off_by_default_so_steam_is_never_asked(self):
        st, r, _ = self.post("/api/mod-updates", {"auto": True})
        self.assertEqual((st, r, self.asked), (200, {"skipped": True, "items": []}, []))

    def test_on_it_asks_once_a_day_and_says_which_mods_are_newer(self):
        self.hub.settings.update(mod_update_alerts=True)
        st, r, _ = self.post("/api/mod-updates", {"auto": True})
        self.assertEqual(st, 200, r)
        self.assertFalse(r["skipped"])
        self.assertEqual({x["remote_id"]: x["status"] for x in r["items"]}, {"111": "update", "222": "current"})
        self.assertEqual(len(self.asked), 1)
        self.assertTrue(self.post("/api/mod-updates", {"auto": True})[1]["skipped"])   # not again the same day
        self.assertEqual(len(self.asked), 1)
        self.assertEqual(len(self.post("/api/mod-updates")[1]), 2)   # the button always asks
        self.assertEqual(len(self.asked), 2)

    def test_the_next_day_it_asks_again(self):
        app = self.hub.app("ck3")
        app.store.update_settings(mod_updates_checked=1)
        self.hub.settings.update(mod_update_alerts=True)
        self.assertFalse(self.post("/api/mod-updates", {"auto": True})[1]["skipped"])
        r = app.mod_updates(self.srv.collection_post, auto=True, now=app.store.settings()["mod_updates_checked"] + app.MOD_UPDATE_EVERY + 1)
        self.assertFalse(r["skipped"])
