"""Randomised and adversarial tests for the load-order engine."""
import random
import time
import unittest

from modmanager import order


def mod(i, deps=(), exists=True):
    return {"id": f"local:m{i}", "name": f"M{i}", "dependencies": [f"M{d}" for d in deps], "incompatible": [],
            "remote_id": None, "exists": exists, "supported_version": ""}


def dag(rng, n, p):
    """Random acyclic graph: mod i may only depend on lower numbers; ids shuffled by the caller."""
    return {f"local:m{i}": mod(i, [j for j in range(i) if rng.random() < p]) for i in range(n)}


def edges(mods, ids):
    idx = {m["name"]: m["id"] for m in mods.values()}
    return [(idx[d], mid) for mid in ids for d in mods[mid]["dependencies"] if idx[d] in ids]


class Property(unittest.TestCase):
    def test_auto_order_is_valid_complete_and_idempotent(self):
        rng = random.Random(1234)
        for trial in range(300):
            n = rng.randint(1, 40)
            mods = dag(rng, n, rng.choice([0.0, 0.05, 0.2, 0.6]))
            ids = list(mods)
            rng.shuffle(ids)
            # random subset enabled
            enabled = [i for i in ids if rng.random() < 0.8] or ids[:1]
            res = order.compute_order(mods, enabled)
            out = res["order"]
            self.assertEqual(sorted(out), sorted(enabled), f"trial {trial}: must be a permutation")
            pos = {m: i for i, m in enumerate(out)}
            for a, b in edges(mods, set(enabled)):
                self.assertLess(pos[a], pos[b], f"trial {trial}: {a} must load before {b}")
            again = order.compute_order(mods, out)
            self.assertEqual(again["order"], out, f"trial {trial}: idempotent")
            self.assertFalse(any(x["moved"] for x in again["notes"].values()))

    def test_already_valid_order_is_never_changed(self):
        rng = random.Random(7)
        for _ in range(100):
            mods = dag(rng, rng.randint(1, 30), 0.2)
            valid = list(mods)  # m0..mN is topological by construction
            self.assertEqual(order.compute_order(mods, valid)["order"], valid)

    def test_unconstrained_mods_keep_relative_user_order(self):
        rng = random.Random(99)
        for _ in range(100):
            n = rng.randint(2, 30)
            mods = dag(rng, n, 0.15)
            ids = list(mods)
            rng.shuffle(ids)
            out = order.compute_order(mods, ids)["order"]
            e = edges(mods, set(ids))
            constrained = {x for ab in e for x in ab}
            free_user = [m for m in ids if m not in constrained]
            free_out = [m for m in out if m not in constrained]
            self.assertEqual(free_user, free_out, "mods with no rules must not be reshuffled")

    def test_manual_mode_never_reorders_and_flags_exactly_the_violations(self):
        rng = random.Random(5)
        for _ in range(100):
            mods = dag(rng, rng.randint(2, 25), 0.3)
            ids = list(mods)
            rng.shuffle(ids)
            res = order.compute_order(mods, ids, auto=False)
            self.assertEqual(res["order"], ids)
            pos = {m: i for i, m in enumerate(ids)}
            bad = {(a, b) for a, b in edges(mods, set(ids)) if pos[a] > pos[b]}
            flagged = {(i["related"], i["module"]) for i in res["issues"] if i["code"] == "wrong_order"}
            self.assertEqual(flagged, bad)

    def test_cycle_members_do_not_poison_the_rest(self):
        mods = {m["id"]: m for m in (mod(0), mod(1, [2]), mod(2, [1]), mod(3, [0]), mod(4, [1]))}
        res = order.compute_order(mods, ["local:m4", "local:m3", "local:m2", "local:m1", "local:m0"])
        self.assertEqual(sorted(res["order"]), sorted(mods))
        pos = {m: i for i, m in enumerate(res["order"])}
        self.assertLess(pos["local:m0"], pos["local:m3"])  # unrelated chain still honoured
        self.assertEqual(sum(i["code"] == "cycle" for i in res["issues"]), 1)

    def test_self_dependency_and_unknown_names_do_not_hang_or_crash(self):
        a = mod(0, [0])
        b = {**mod(1), "dependencies": ["Ghost", ""]}
        res = order.compute_order({a["id"]: a, b["id"]: b}, [a["id"], b["id"]])
        self.assertEqual(res["order"], [a["id"], b["id"]])
        self.assertIn("missing_dependency", {i["code"] for i in res["issues"]})

    def test_dependency_on_disabled_mod_creates_no_ordering_edge(self):
        mods = {m["id"]: m for m in (mod(0), mod(1, [0]))}
        res = order.compute_order(mods, ["local:m1"])  # m0 not enabled
        self.assertEqual(res["order"], ["local:m1"])
        self.assertEqual([i["code"] for i in res["issues"]], ["disabled_dependency"])

    def test_transitive_chain_pulled_in_by_enable_fix_loads_in_order(self):
        mods = {m["id"]: m for m in (mod(0), mod(1, [0]), mod(2, [1]), mod(3, [2]))}
        need = order.missing_required(mods, ["local:m3"])
        self.assertEqual(need, ["local:m0", "local:m1", "local:m2"])
        out = order.compute_order(mods, ["local:m3"] + need)["order"]
        self.assertEqual(out, ["local:m0", "local:m1", "local:m2", "local:m3"])

    def test_long_chain_and_large_playset_are_fast(self):
        n = 3000
        mods = {f"local:m{i}": mod(i, [i - 1] if i else []) for i in range(n)}
        ids = list(reversed(list(mods)))
        t = time.time()
        out = order.compute_order(mods, ids)["order"]
        self.assertEqual(out, list(mods))
        self.assertLess(time.time() - t, 3.0, "3000-mod chain must sort quickly")
        # deep chain must not hit the recursion limit
        self.assertEqual(len(order.missing_required(mods, [f"local:m{n - 1}"])), n - 1)

    def test_explanations_name_every_dependency(self):
        mods = {m["id"]: m for m in (mod(0), mod(1), mod(2, [0, 1]))}
        r = order.compute_order(mods, ["local:m2", "local:m1", "local:m0"])
        why = r["notes"]["local:m2"]["reason"]
        self.assertIn("M0", why)
        self.assertIn("M1", why)
        self.assertEqual(r["notes"]["local:m0"]["reason"], "Keeps the position you gave it.")

    def test_sort_playset_properties(self):
        rng = random.Random(42)
        for _ in range(100):
            mods = dag(rng, rng.randint(1, 20), 0.3)
            ids = list(mods) + ["local:ghost"]
            rng.shuffle(ids)
            off = [i for i in ids if rng.random() < 0.3]
            out = order.sort_playset(mods, ids, off)
            self.assertEqual(sorted(out), sorted(ids))
            self.assertEqual([i for i, m in enumerate(out) if m in off], [i for i, m in enumerate(ids) if m in off],
                             "disabled mods keep their slots")
            self.assertEqual(order.sort_playset(mods, out, off), out, "idempotent")
            on = [m for m in out if m not in off and m in mods]
            pos = {m: i for i, m in enumerate(on)}
            for a, b in edges(mods, set(on)):
                self.assertLess(pos[a], pos[b])

    def test_workshop_ids_and_duplicate_names(self):
        a = {**mod(0), "name": "Lib", "id": "ws:1", "remote_id": "1"}
        b = {**mod(1), "name": "Lib", "id": "local:copy"}  # same display name
        c = {**mod(2), "dependencies": ["1"]}  # depends by workshop id
        mods = {m["id"]: m for m in (a, b, c)}
        res = order.compute_order(mods, ["local:m2", "local:copy", "ws:1"])
        self.assertLess(res["order"].index("ws:1"), res["order"].index("local:m2"))
        self.assertEqual(sum(i["code"] == "duplicate" for i in res["issues"]), 2)


if __name__ == "__main__":
    unittest.main()
