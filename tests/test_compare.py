import itertools
import random
import unittest

from modmanager.compare import _lis, compare_playsets


def ps(mods, disabled=(), **kw):
    return {"mods": list(mods), "disabled": list(disabled), "auto_sort": True, "separate_saves": False,
            "launch_args": [], "notes": "", **kw}


class Lis(unittest.TestCase):
    def test_lis_is_longest_and_increasing(self):
        rng = random.Random(1)
        for _ in range(300):
            seq = rng.sample(range(40), rng.randint(0, 12))
            idx = _lis(seq)
            vals = [seq[i] for i in idx]
            self.assertEqual(vals, sorted(vals))
            self.assertEqual(idx, sorted(idx))
            best = max((len(c) for r in range(len(seq) + 1) for c in itertools.combinations(seq, r)
                        if list(c) == sorted(c)), default=0) if len(seq) <= 10 else len(idx)
            self.assertEqual(len(idx), best)


class Compare(unittest.TestCase):
    def test_identical(self):
        r = compare_playsets({}, ps("abc"), ps("abc"))
        self.assertTrue(r["identical"])
        self.assertEqual(r["same"], list("abc"))

    def test_only_in_each_and_state_differences(self):
        a = ps("abcd", disabled="d")
        b = ps("acxd", disabled="c")
        r = compare_playsets({}, a, b)
        self.assertEqual(r["only_a"], ["b"])                 # enabled in A, absent in B
        self.assertEqual(r["only_b"], ["x"])
        self.assertEqual(r["state"], [{"id": "c", "a": "enabled", "b": "disabled"},
                                      {"id": "d", "a": "disabled", "b": "enabled"}])
        self.assertFalse(r["identical"])

    def test_disabled_in_a_but_absent_in_b_is_not_a_difference(self):
        r = compare_playsets({}, ps("ab", disabled="b"), ps("a"))
        self.assertTrue(r["identical"])

    def test_moved_is_minimal(self):
        # one mod jumped from the end to the front: only that one is "moved", not everything in between
        r = compare_playsets({}, ps("abcde"), ps("eabcd"))
        self.assertEqual([m["id"] for m in r["moved"]], ["e"])
        self.assertEqual((r["moved"][0]["a"], r["moved"][0]["b"]), (5, 1))
        self.assertEqual(r["same"], list("abcd"))

    def test_swap_reports_one_mover_and_reverse_reports_all_but_one(self):
        self.assertEqual(len(compare_playsets({}, ps("abc"), ps("acb"))["moved"]), 1)
        self.assertEqual(len(compare_playsets({}, ps("abcd"), ps("dcba"))["moved"]), 3)

    def test_moved_ignores_mods_that_are_not_common(self):
        r = compare_playsets({}, ps("axbyc"), ps("abc"))
        self.assertEqual(r["moved"], [])
        self.assertEqual((r["only_a"], r["only_b"]), (["x", "y"], []))

    def test_settings(self):
        r = compare_playsets({}, ps("a", auto_sort=True, notes="n"), ps("a", auto_sort=False, launch_args=["-x"]))
        self.assertEqual({s["field"] for s in r["settings"]}, {"auto_sort", "launch_args", "notes"})
        self.assertFalse(r["identical"])

    def test_symmetry_and_applying_the_diff_makes_them_equal(self):
        rng = random.Random(9)
        for _ in range(200):
            pool = list("abcdefghij")
            a = rng.sample(pool, rng.randint(0, 8))
            b = rng.sample(pool, rng.randint(0, 8))
            da = rng.sample(a, rng.randint(0, len(a))) if a else []
            db = rng.sample(b, rng.randint(0, len(b))) if b else []
            A, B = ps(a, da), ps(b, db)
            ab, ba = compare_playsets({}, A, B), compare_playsets({}, B, A)
            self.assertEqual(ab["only_a"], ba["only_b"])
            self.assertEqual(ab["only_b"], ba["only_a"])
            self.assertEqual(sorted(s["id"] for s in ab["state"]), sorted(s["id"] for s in ba["state"]))
            self.assertEqual(len(ab["moved"]), len(ba["moved"]))
            self.assertEqual(ab["identical"], ba["identical"])
            # enabled sets: A's enabled = common-enabled + only_a + (enabled-in-A, disabled-in-B)
            ea = {m for m in a if m not in da}
            eb = {m for m in b if m not in db}
            both = ea & eb
            self.assertEqual(ea, both | set(ab["only_a"]) | {s["id"] for s in ab["state"] if s["a"] == "enabled"})
            self.assertEqual(eb, both | set(ab["only_b"]) | {s["id"] for s in ab["state"] if s["b"] == "enabled"})
            self.assertEqual(sorted(ab["same"] + [m["id"] for m in ab["moved"]]), sorted(both))


if __name__ == "__main__":
    unittest.main()
