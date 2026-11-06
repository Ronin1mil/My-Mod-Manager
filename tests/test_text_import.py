"""Import a playset from a plain text mod list (pasted, or a .txt file) and Export as text."""
import unittest

from modmanager import games
from modmanager.store import text_to_shared
from tests.helpers import GameCase, mkmod, mkworkshop

LIST = """# Playset: From Reddit
# Game: ck3
https://steamcommunity.com/sharedfiles/filedetails/?id=2217567218&searchtext=
- 2216670956  Second One
1. my local mod
[off] 1234567890
* Not Installed Anywhere

"""


class Parsing(unittest.TestCase):
    def test_links_ids_names_bullets_comments_and_off(self):
        doc = text_to_shared(LIST)
        self.assertEqual((doc["name"], doc["game"]), ("From Reddit", "ck3"))
        self.assertEqual([(m["remote_id"], m["name"], m["enabled"]) for m in doc["mods"]],
                         [("2217567218", None, True), ("2216670956", "Second One", True), (None, "my local mod", True),
                          ("1234567890", None, False), (None, "Not Installed Anywhere", True)])

    def test_a_given_name_wins_over_the_comment_and_bad_text_is_refused(self):
        self.assertEqual(text_to_shared("# Playset: X\n123456", "Mine")["name"], "Mine")
        for bad in ("", "# only comments\n\n", None, "x\n" * 6000, "a" * 600 * 1024):
            with self.assertRaises(ValueError):
                text_to_shared(bad)


class OverHttp(GameCase):
    GAME = games.CK3

    def setUp(self):
        super().setUp()
        for wid, name in ((2217567218, "First One"), (2216670956, "Second One"), (1234567890, "Third One")):
            mkworkshop(self.ws(), wid, name)
        mkmod(self.user(), "local", "My Local Mod")
        self.post("/api/rescan")

    def test_a_pasted_list_becomes_a_playset_in_that_order(self):
        st, r, _ = self.post("/api/import", {"text": LIST, "name": "Pasted"})
        self.assertEqual(st, 200, r)
        self.assertEqual(r["missing"], ["Not Installed Anywhere"])
        ps = next(p for p in self.req("GET", "/api/state")[1]["playsets"] if p["id"] == r["id"])
        self.assertEqual(ps["name"], "Pasted")
        self.assertEqual(ps["mods"], ["ws:2217567218", "ws:2216670956", "local:local", "ws:1234567890"])   # names match whatever the case
        self.assertEqual(ps["disabled"], ["ws:1234567890"])

    def test_export_as_text_reads_back_the_same_playset(self):
        pid = self.new_playset(["ws:2216670956", "local:local", "ws:2217567218"])
        self.post(f"/api/playsets/{pid}/update", {"disabled": ["ws:2217567218"]})
        st, x, _ = self.req("GET", f"/api/playsets/{pid}/share-text")
        self.assertEqual(st, 200, x)
        self.assertIn("2216670956  Second One", x["text"])
        self.assertIn("[off] 2217567218  First One", x["text"])
        r = self.post("/api/import", {"text": x["text"]})[1]
        ps = next(p for p in self.req("GET", "/api/state")[1]["playsets"] if p["id"] == r["id"])
        self.assertEqual((ps["name"], ps["mods"], ps["disabled"]), ("T", ["ws:2216670956", "local:local", "ws:2217567218"], ["ws:2217567218"]))

    def test_a_hand_made_json_file_can_be_this_short(self):
        doc = {"name": "By hand", "game": "ck3", "mods": [
            "https://steamcommunity.com/sharedfiles/filedetails/?id=2216670956", "my local mod",
            {"workshop_id": "1234567890", "enabled": False, "note": "crashes"}, "Not Here"]}
        st, r, _ = self.post("/api/import", doc)
        self.assertEqual((st, r.get("missing")), (200, ["Not Here"]), r)
        ps = next(p for p in self.req("GET", "/api/state")[1]["playsets"] if p["id"] == r["id"])
        self.assertEqual((ps["name"], ps["mods"], ps["disabled"]), ("By hand", ["ws:2216670956", "local:local", "ws:1234567890"], ["ws:1234567890"]))
        self.assertEqual(ps["mod_notes"], {"ws:1234567890": "crashes"})
        self.assertEqual(self.post("/api/import", {"name": "no mods key"})[0], 400)

    def test_a_list_for_another_game_is_refused(self):
        st, r, _ = self.post("/api/import", {"text": "# Game: eu5\n2217567218"})
        self.assertEqual(st, 400)
        self.assertIn("eu5", r["error"])


if __name__ == "__main__":
    unittest.main()
