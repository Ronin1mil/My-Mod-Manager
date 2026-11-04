import tempfile
import unittest
from pathlib import Path

from modmanager import order, scan, smartsort
from tests.test_order import ids, lib, mod


def clash(kind, path, *names, winner=None, severity="warn"):
    m = ids(*names)
    return {"kind": kind, "severity": severity, "path": path, "mods": m, "winner": winner or m[-1]}


class Plan(unittest.TestCase):
    def sort(self, mods, names, conflicts, sizes=None):
        nodes = ids(*names)
        sizes = {f"local:{k}": v for k, v in (sizes or {}).items()}
        p = smartsort.plan(mods, nodes, conflicts, sizes)
        return order.compute_order(mods, nodes, True, "", p["edges"])["order"], p

    def test_small_tweak_loads_after_big_overhaul(self):
        mods = lib(mod("Tweak"), mod("Overhaul"))
        got, p = self.sort(mods, ["Overhaul", "Tweak"][::-1], [clash("file", "common/a.txt", "Tweak", "Overhaul")],
                           {"Tweak": 3, "Overhaul": 400})
        self.assertEqual(got, ids("Overhaul", "Tweak"))
        self.assertIn("smaller mod", p["report"]["rules"][0]["why"])

    def test_similar_size_keeps_the_users_order_and_is_reported(self):
        mods = lib(mod("A"), mod("B"))
        got, p = self.sort(mods, ["B", "A"], [clash("file", "common/a.txt", "B", "A")], {"A": 50, "B": 60})
        self.assertEqual(got, ids("B", "A"))
        self.assertEqual(p["report"]["tie_count"], 1)
        self.assertEqual(p["edges"], [])

    def test_patch_by_name_loads_after(self):
        mods = lib(mod("Big Thing"), mod("Big Thing Compatibility Patch"))
        got, _ = self.sort(mods, ["Big Thing Compatibility Patch", "Big Thing"],
                           [clash("file", "x.txt", "Big Thing Compatibility Patch", "Big Thing")], {})
        self.assertEqual(got, ids("Big Thing", "Big Thing Compatibility Patch"))

    def test_compatch_wording_beats_size(self):
        mods = lib(mod("Tiny"), mod("Giant Compatch"))
        got, _ = self.sort(mods, ["Giant Compatch", "Tiny"], [clash("definition", "x: y", "Giant Compatch", "Tiny")],
                           {"Giant Compatch": 900, "Tiny": 2})
        self.assertEqual(got, ids("Tiny", "Giant Compatch"))

    def test_replace_path_mod_goes_first(self):
        mods = lib(mod("Addon"), mod("Total Conversion"))
        got, p = self.sort(mods, ["Addon", "Total Conversion"],
                           [{"kind": "replace", "severity": "warn", "path": "history/ (4 files)",
                             "mods": ids("Addon", "Total Conversion"), "winner": "local:Total Conversion"}])
        self.assertEqual(got, ids("Total Conversion", "Addon"))
        self.assertIn("replaces a folder", p["report"]["rules"][0]["why"])

    def test_dependency_always_wins_over_a_rule(self):
        # Small needs Big, so Big must load first even though the rule would put the big mod first anyway; the reverse
        # pair (Big needs Small) must keep Small first: the rule that wants it the other way is dropped, not applied.
        mods = lib(mod("Small"), mod("Big", ["Small"]))
        got, p = self.sort(mods, ["Small", "Big"], [clash("file", "a.txt", "Small", "Big")], {"Small": 2, "Big": 300})
        self.assertEqual(got, ids("Small", "Big"))
        self.assertEqual(p["report"]["dropped"], 1)

    def test_no_loop_from_contradicting_rules(self):
        mods = lib(mod("A"), mod("B"), mod("C"))
        cs = [clash("file", "1.txt", "A", "B"), clash("file", "2.txt", "B", "C"), clash("file", "3.txt", "A", "C")]
        got, _ = self.sort(mods, ["A", "B", "C"], cs, {"A": 10, "B": 40, "C": 160})
        self.assertEqual(sorted(got), sorted(ids("A", "B", "C")))
        self.assertEqual(got, ids("C", "B", "A"))   # bigger first, consistently

    def test_intentional_replace_and_info_clashes_are_ignored(self):
        mods = lib(mod("Tweak"), mod("Overhaul"))
        cs = [clash("definition", "x: y", "Tweak", "Overhaul", severity="info"), clash("patch", "x: z", "Tweak", "Overhaul", severity="info")]
        got, p = self.sort(mods, ["Tweak", "Overhaul"], cs, {"Tweak": 1, "Overhaul": 99})
        self.assertEqual(got, ids("Tweak", "Overhaul"))
        self.assertEqual(p["report"]["tie_count"], 0)

    def test_base_game_clashes_do_not_count(self):
        mods = lib(mod("A"), mod("B"))
        cs = [{"kind": "file", "severity": "warn", "path": "a.txt", "mods": [scan.VANILLA, "local:A"], "winner": "local:A"}]
        got, p = self.sort(mods, ["B", "A"], cs, {"A": 1, "B": 90})
        self.assertEqual(got, ids("B", "A"))
        self.assertEqual(p["report"]["tie_count"], 0)

    def test_reason_is_added_to_the_position_note(self):
        mods = lib(mod("Tweak"), mod("Overhaul"))
        nodes = ids("Tweak", "Overhaul")
        p = smartsort.plan(mods, nodes, [clash("file", "a.txt", "Tweak", "Overhaul")], {"local:Tweak": 1, "local:Overhaul": 99})
        r = order.compute_order(mods, nodes, True, "", p["edges"])
        self.assertIn("smaller mod", r["notes"]["local:Tweak"]["reason"])
        self.assertTrue(r["notes"]["local:Tweak"]["moved"])

    def test_auto_off_ignores_extra_rules(self):
        mods = lib(mod("Tweak"), mod("Overhaul"))
        nodes = ids("Tweak", "Overhaul")
        p = smartsort.plan(mods, nodes, [clash("file", "a.txt", "Tweak", "Overhaul")], {"local:Tweak": 1, "local:Overhaul": 99})
        r = order.compute_order(mods, nodes, False, "", p["edges"])
        self.assertEqual(r["order"], nodes)
        self.assertEqual(r["issues"], [])


class WithRealFiles(unittest.TestCase):
    def test_find_conflicts_to_sorted_playset(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            mods = {}
            for name, files in {"Tweak": ["common/goods/g.txt"],
                                "Overhaul": ["common/goods/g.txt", "common/a.txt", "common/b.txt", "common/c.txt", "common/d.txt"]}.items():
                for f in files:
                    p = root / name / f
                    p.parent.mkdir(parents=True, exist_ok=True)
                    p.write_text("x = { }")
                m = mod(name)
                m.update({"root": str(root / name), "replace_path": []})
                mods[m["id"]] = m
            nodes = ids("Tweak", "Overhaul")
            cache = {}
            conflicts = scan.find_conflicts(mods, nodes, cache)
            sizes = {i: len(cache[(mods[i]["root"], ())]) for i in nodes}
            p = smartsort.plan(mods, nodes, conflicts, sizes)
            self.assertEqual(order.sort_playset(mods, nodes, [], "", p["edges"]), ids("Overhaul", "Tweak"))


if __name__ == "__main__":
    unittest.main()
