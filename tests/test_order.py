import unittest

from modmanager import order


def mod(name, deps=(), inc=(), rid=None, supported=""):
    return {"id": f"local:{name}", "name": name, "dependencies": list(deps), "incompatible": list(inc),
            "remote_id": rid, "exists": True, "supported_version": supported}


def lib(*ms):
    return {m["id"]: m for m in ms}


def ids(*names):
    return [f"local:{n}" for n in names]


class T(unittest.TestCase):
    def test_dependencies_load_first_with_reason(self):
        mods = lib(mod("Lib"), mod("A", ["Lib"]))
        r = order.compute_order(mods, ids("A", "Lib"))
        self.assertEqual(r["order"], ids("Lib", "A"))
        self.assertIn("Loads after Lib", r["notes"]["local:A"]["reason"])
        self.assertTrue(r["notes"]["local:A"]["moved"])

    def test_user_order_preserved_when_unconstrained(self):
        mods = lib(mod("B"), mod("C"), mod("D"))
        r = order.compute_order(mods, ids("D", "B", "C"))
        self.assertEqual(r["order"], ids("D", "B", "C"))
        self.assertFalse(any(n["moved"] for n in r["notes"].values()))

    def test_idempotent_and_deterministic(self):
        mods = lib(mod("L"), mod("A", ["L"]), mod("B", ["L"]), mod("C", ["A", "B"]))
        r1 = order.compute_order(mods, ids("C", "B", "A", "L"))
        r2 = order.compute_order(mods, r1["order"])
        self.assertEqual(r1["order"], r2["order"])

    def test_cycle_does_not_hang(self):
        mods = lib(mod("A", ["B"]), mod("B", ["A"]), mod("C"))
        r = order.compute_order(mods, ids("A", "B", "C"))
        self.assertEqual(len(r["order"]), 3)
        self.assertIn("cycle", {i["code"] for i in r["issues"]})

    def test_disabled_and_missing_dependency_with_fix(self):
        mods = lib(mod("Lib"), mod("A", ["Lib", "Ghost"]))
        r = order.compute_order(mods, ids("A"))
        by = {i["code"]: i for i in r["issues"]}
        self.assertEqual(by["disabled_dependency"]["fix"], {"kind": "enable", "id": "local:Lib"})
        self.assertIsNone(by["missing_dependency"]["fix"])
        self.assertEqual(order.missing_required(mods, ids("A")), ids("Lib"))

    def test_transitive_missing_required(self):
        mods = lib(mod("L2"), mod("L1", ["L2"]), mod("A", ["L1"]))
        self.assertEqual(order.missing_required(mods, ids("A")), ids("L2", "L1"))

    def test_manual_mode_flags_wrong_order_with_autosort_fix(self):
        mods = lib(mod("Lib"), mod("A", ["Lib"]))
        r = order.compute_order(mods, ids("A", "Lib"), auto=False)
        self.assertEqual(r["order"], ids("A", "Lib"))
        w = [i for i in r["issues"] if i["code"] == "wrong_order"][0]
        self.assertEqual(w["fix"], {"kind": "autosort"})

    def test_workshop_id_dependency_resolves(self):
        mods = lib(mod("Lib", rid="555"), mod("A", ["ugc_555"]))
        self.assertEqual(order.compute_order(mods, ids("A", "Lib"))["order"], ids("Lib", "A"))

    def test_incompatible_reported_once(self):
        mods = lib(mod("A", inc=["B"]), mod("B", inc=["A"]))
        r = order.compute_order(mods, ids("A", "B"))
        self.assertEqual(sum(i["code"] == "incompatible" for i in r["issues"]), 1)

    def test_duplicates_and_missing_module(self):
        mods = lib(mod("A"))
        r = order.compute_order(mods, ids("A", "A", "Gone"))
        self.assertEqual(r["order"], ids("A"))
        self.assertIn("missing_module", {i["code"] for i in r["issues"]})

    def test_version_matches(self):
        self.assertTrue(order.version_matches("1.7.*", "1.7.6"))
        self.assertTrue(order.version_matches("1.7", "1.7.6"))
        self.assertFalse(order.version_matches("1.6.*", "1.7.6"))
        self.assertTrue(order.version_matches("", "1.7.6"))

    def test_sort_playset_keeps_disabled_slots(self):
        mods = lib(mod("Lib"), mod("A", ["Lib"]), mod("Off"))
        out = order.sort_playset(mods, ids("A", "Off", "Lib"), ids("Off"))
        self.assertEqual(out, ids("Lib", "Off", "A"))
        # uninstalled ids survive and sorting twice is stable
        out2 = order.sort_playset(mods, ids("A", "Ghost", "Lib"), [])
        self.assertEqual(sorted(out2), sorted(ids("A", "Ghost", "Lib")))
        self.assertEqual(order.sort_playset(mods, out2, []), out2)


if __name__ == "__main__":
    unittest.main()
