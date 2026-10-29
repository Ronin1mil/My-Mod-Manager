import tempfile
import unittest
from pathlib import Path

from modmanager.library import CHANGE_VISIBLE_SECS, Library


def mods(**vs):
    return {k: {"id": k, "name": k, "version": v} for k, v in vs.items()}


class T(unittest.TestCase):
    def test_change_tracking(self):
        with tempfile.TemporaryDirectory() as r:
            lib = Library(Path(r) / "l.json")
            d = lib.merge(mods(a="1", b="1"), now=100)
            self.assertEqual((d["added"], lib.change("a", 100)), (0, "none"))  # first scan marks nothing
            d = lib.merge(mods(a="2", b="1", c="1"), now=200)
            self.assertEqual((d["added"], d["updated"], d["removed"]), (1, 1, 0))
            self.assertEqual((lib.change("a", 200), lib.change("c", 200), lib.change("b", 200)),
                             ("updated", "new", "none"))
            d = lib.merge(mods(a="2", c="1"), now=300)
            self.assertEqual(d["removed"], 1)
            self.assertEqual(lib.removed(), [{"id": "b", "name": "b"}])
            d = lib.merge(mods(a="2", b="1", c="1"), now=400)  # came back
            self.assertEqual((d["added"], lib.change("b", 400), lib.removed()), (1, "new", []))
            self.assertEqual(lib.change("b", 400 + CHANGE_VISIBLE_SECS + 1), "none")  # fades
            self.assertEqual(Library(Path(r) / "l.json").change("b", 400), "new")  # persisted

    def test_corrupt_file_is_ignored(self):
        with tempfile.TemporaryDirectory() as r:
            (Path(r) / "l.json").write_text("{not json")
            self.assertEqual(Library(Path(r) / "l.json").data["entries"], {})


if __name__ == "__main__":
    unittest.main()


class StoredTags(unittest.TestCase):
    def test_tags_and_source_are_stored_and_counted(self):
        import tempfile
        from pathlib import Path
        with tempfile.TemporaryDirectory() as d:
            lib = Library(Path(d) / "library.json")
            lib.merge({"ws:1": {"name": "A", "version": "1", "tags": ["Gameplay", "Balance"], "source": "workshop"},
                       "local:B": {"name": "B", "version": "1", "tags": ["Gameplay"], "source": "local"},
                       "local:C": {"name": "C", "version": "1", "tags": [], "source": "local"}})
            self.assertEqual(lib.tag_counts(), {"Gameplay": 2, "Balance": 1})
            again = Library(Path(d) / "library.json")  # kept on disk
            self.assertEqual(again.data["entries"]["ws:1"]["tags"], ["Gameplay", "Balance"])
            self.assertEqual(again.data["entries"]["local:B"]["source"], "local")
            # a changed tag list replaces the old one at the next scan
            again.merge({"ws:1": {"name": "A", "version": "1", "tags": ["Map"], "source": "workshop"}})
            self.assertEqual(again.data["entries"]["ws:1"]["tags"], ["Map"])
