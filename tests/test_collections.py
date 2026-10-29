import unittest
from unittest import mock

from modmanager import collections, games, presets


def fake_post(path, fields):
    if "GetCollectionDetails" in path:
        return {"response": {"collectiondetails": [{"result": 1, "children": [
            {"publishedfileid": "30", "sortorder": 2}, {"publishedfileid": "10", "sortorder": 1},
            {"publishedfileid": "10", "sortorder": 3}, {"publishedfileid": "x; rm", "sortorder": 4}]}]}}
    return {"response": {"publishedfiledetails": [
        {"publishedfileid": "99", "title": "My Big Stack!", "description": "hello"},
        {"publishedfileid": "10", "title": "Core"}, {"publishedfileid": "30", "title": "Addon"}]}}


class T(unittest.TestCase):
    def test_parse(self):
        for ok in ("99", "https://steamcommunity.com/sharedfiles/filedetails/?id=99",
                   "https://steamcommunity.com/workshop/filedetails/?l=en&id=99&x=1"):
            self.assertEqual(collections.parse_collection_id(ok), "99")
        for bad in ("", "evil", "https://evil.example/?id=99", "steamcommunity.com.evil.io/sharedfiles/filedetails/?id=9", None):
            with self.assertRaises(ValueError):
                collections.parse_collection_id(bad)

    def test_import_makes_valid_ordered_preset(self):
        doc = collections.import_collection(games.CK3, "99", fake_post)
        p = presets.validate(doc, "ck3")
        self.assertEqual([m["workshop_id"] for m in p["mods"]], ["10", "30"])  # sorted, deduped, junk dropped
        self.assertEqual((p["name"], p["id"], p["status"]), ("My Big Stack!", "my-big-stack", "unverified"))
        self.assertEqual(p["mods"][0]["name"], "Core")

    def test_errors_are_clear(self):
        with self.assertRaises(ValueError):
            collections.import_collection(games.CK3, "99", lambda *a: {"response": {"collectiondetails": [{"result": 9}]}})
        with self.assertRaises(ValueError):
            collections.import_collection(games.CK3, "99", lambda *a: {"response": {"collectiondetails": [{"result": 1, "children": []}]}})

    def test_names_failure_still_gives_ids(self):
        def post(path, fields):
            if "Collection" in path:
                return fake_post(path, fields)
            raise ValueError("down")
        doc = collections.import_collection(games.CK3, "99", post)
        self.assertEqual([m["name"] for m in doc["mods"]], ["10", "30"])
        self.assertEqual(doc["id"], "collection-99")
