"""Undo / Redo of playset changes, restoring deleted playsets, and the per-mod notes of a playset."""
import json
import tempfile
import unittest
from pathlib import Path

from modmanager import games
from modmanager.store import UNDO_DEPTH, Store
from tests.helpers import GameCase, mkmod


class StoreHistory(unittest.TestCase):
    def setUp(self):
        t = tempfile.TemporaryDirectory()
        self.addCleanup(t.cleanup)
        self.path = Path(t.name) / "p.json"
        self.s = Store(self.path)

    def test_undo_and_redo_walk_back_and_forth(self):
        pid = self.s.create("A", ["a"])
        self.assertEqual(self.s.with_history(self.s.get(pid))["can_undo"], 0)   # making it is not an edit
        self.s.update(pid, mods=["a", "b"])
        self.s.update(pid, name="B", disabled=["a"])
        self.assertEqual((self.s.step(pid, "undo")["name"], self.s.get(pid)["disabled"]), ("A", []))
        self.assertEqual(self.s.step(pid, "undo")["mods"], ["a"])
        with self.assertRaises(ValueError):
            self.s.step(pid, "undo")
        self.assertEqual(self.s.step(pid, "redo")["mods"], ["a", "b"])
        self.assertEqual(self.s.step(pid, "redo")["name"], "B")
        with self.assertRaises(ValueError):
            self.s.step(pid, "redo")

    def test_a_new_edit_clears_redo_and_a_no_op_records_nothing(self):
        pid = self.s.create("A", ["a"])
        self.s.update(pid, mods=["a", "b"])
        self.s.step(pid, "undo")
        self.s.update(pid, notes="hi")
        h = self.s.with_history(self.s.get(pid))
        self.assertEqual((h["can_undo"], h["can_redo"]), (1, 0))
        self.s.update(pid, notes="hi")   # nothing changed
        self.assertEqual(self.s.with_history(self.s.get(pid))["can_undo"], 1)
        self.s.update(pid, record=False, notes="x")
        self.assertEqual(self.s.with_history(self.s.get(pid))["can_undo"], 1)

    def test_history_is_capped_and_survives_a_restart(self):
        pid = self.s.create("A")
        for i in range(UNDO_DEPTH + 5):
            self.s.update(pid, notes=str(i))
        again = Store(self.path)
        self.assertEqual(again.with_history(again.get(pid))["can_undo"], UNDO_DEPTH)
        self.assertEqual(again.step(pid, "undo")["notes"], str(UNDO_DEPTH + 3))

    def test_deleted_playsets_can_be_restored(self):
        a = self.s.create("Keep me", ["a"], notes="n")
        self.s.update(a, mods=["a", "b"])
        self.s.delete(a)
        self.assertEqual([(t["id"], t["name"], t["mods"]) for t in self.s.trash()], [(a, "Keep me", 2)])
        self.assertEqual(self.s.restore(a), a)
        self.assertEqual((self.s.get(a)["mods"], self.s.get(a)["notes"]), (["a", "b"], "n"))
        self.assertEqual(self.s.trash(), [])
        with self.assertRaises(KeyError):
            self.s.restore(a)

    def test_the_trash_keeps_only_the_last_ten(self):
        ids = [self.s.create(f"P{i}") for i in range(12)]
        for pid in ids:
            self.s.delete(pid)
        self.assertEqual([t["name"] for t in self.s.trash()][:2], ["P11", "P10"])
        self.assertEqual(len(self.s.trash()), 10)

    def test_mod_notes_are_validated_copied_and_shared(self):
        pid = self.s.create("A", ["a", "b"])
        self.s.update(pid, mod_notes={"a": "  crashes with b  ", "b": "   "})
        self.assertEqual(self.s.get(pid)["mod_notes"], {"a": "crashes with b"})
        for bad in ({"a": "x" * 301}, {"a": 1}, ["a"], {"": "x"}):
            with self.assertRaises(ValueError):
                self.s.update(pid, mod_notes=bad)
        self.assertEqual(self.s.get(self.s.duplicate(pid, "Copy"))["mod_notes"], {"a": "crashes with b"})
        mods = {"a": {"id": "a", "name": "Mod A", "remote_id": "1"}, "b": {"id": "b", "name": "Mod B", "remote_id": None}}
        doc = self.s.share(pid, mods, "ck3")
        self.assertEqual(doc["mods"][0]["note"], "crashes with b")
        self.assertNotIn("note", doc["mods"][1])
        other = Store(self.path.with_name("q.json"))
        new, missing = other.import_shared(json.loads(json.dumps(doc)), mods, "ck3")
        self.assertEqual((other.get(new)["mod_notes"], missing), ({"a": "crashes with b"}, []))


class OverHttp(GameCase):
    GAME = games.CK3

    def test_one_edit_with_its_auto_sort_is_one_undo_step(self):
        mkmod(self.user(), "lib", "Lib")
        mkmod(self.user(), "big", "Big", deps=["Lib"])
        pid = self.new_playset(["local:lib"])
        st, ps, _ = self.post(f"/api/playsets/{pid}/update", {"mods": ["local:big", "local:lib"]})
        self.assertEqual((st, ps["mods"], ps["can_undo"], ps["can_redo"]), (200, ["local:lib", "local:big"], 1, 0))
        st, ps, _ = self.post(f"/api/playsets/{pid}/undo")
        self.assertEqual((st, ps["mods"], ps["can_undo"], ps["can_redo"]), (200, ["local:lib"], 0, 1))
        self.assertEqual(self.post(f"/api/playsets/{pid}/undo")[0], 400)
        ps = self.post(f"/api/playsets/{pid}/redo")[1]
        self.assertEqual(ps["mods"], ["local:lib", "local:big"])
        state = self.req("GET", "/api/state")[1]
        self.assertEqual([(p["can_undo"], p["can_redo"]) for p in state["playsets"]], [(1, 0)])

    def test_restore_a_deleted_playset(self):
        pid = self.new_playset([])
        self.post(f"/api/playsets/{pid}/delete")
        state = self.req("GET", "/api/state")[1]
        self.assertEqual(([p["id"] for p in state["playsets"]], [t["id"] for t in state["trash"]]), ([], [pid]))
        st, r, _ = self.post(f"/api/playsets/{pid}/restore")
        self.assertEqual((st, r["id"]), (200, pid))
        self.assertEqual([p["id"] for p in self.req("GET", "/api/state")[1]["playsets"]], [pid])
        self.assertEqual(self.post("/api/playsets/nope/restore")[0], 404)

    def test_the_no_mods_playset_has_no_history(self):
        self.assertEqual(self.post("/api/playsets/nomods/undo")[0], 400)


if __name__ == "__main__":
    unittest.main()
