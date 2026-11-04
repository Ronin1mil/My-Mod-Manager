import unittest

from modmanager import games
from tests.helpers import GameCase, mkmod


class Winners(GameCase):
    GAME = games.VIC3

    def setUp(self):
        super().setUp()
        u = self.user()
        mkmod(u, "Big", files={f"common/goods/{n}.txt": "g = { }" for n in ("x", "a", "b", "c", "d", "e")})
        mkmod(u, "Small", files={"common/goods/x.txt": "g = { }"})
        mkmod(u, "Needs", deps=["Big"])
        self.post("/api/rescan", {})
        self.pid = self.new_playset(["local:Big", "local:Small"])

    def order(self):
        return self.playset()["mods"]

    def playset(self):
        return [p for p in self.req("GET", "/api/state")[1]["playsets"] if p["id"] == self.pid][0]

    def test_conflicts_report_each_pair_with_counts(self):
        st, res, _ = self.req("GET", f"/api/conflicts/{self.pid}")
        self.assertEqual(st, 200)
        self.assertEqual(len(res["pairs"]), 1)
        p = res["pairs"][0]
        self.assertEqual({p["a"], p["b"]}, {"local:Big", "local:Small"})
        self.assertEqual(p["files"], 1)
        self.assertIn("common/goods/x.txt", p["examples"])

    def test_choosing_a_winner_reorders_and_is_remembered(self):
        self.assertEqual(self.order(), ["local:Big", "local:Small"])   # Small loads last: Small wins
        st, ps, _ = self.post(f"/api/playsets/{self.pid}/winner", {"pairs": [["local:Big", "local:Small"]]})
        self.assertEqual(st, 200)
        self.assertEqual(ps["mods"], ["local:Small", "local:Big"])
        self.assertEqual(ps["winners"], [["local:Big", "local:Small"]])

    def test_sort_now_keeps_the_choice_against_its_own_size_rule(self):
        self.post(f"/api/playsets/{self.pid}/winner", {"pairs": [["local:Big", "local:Small"]]})
        st, res, _ = self.post(f"/api/playsets/{self.pid}/smartsort", {})
        self.assertEqual(st, 200)
        self.assertEqual(res["playset"]["mods"], ["local:Small", "local:Big"])
        self.assertTrue(any("you chose" in r["why"] for r in res["report"]["rules"]))

    def test_a_dependency_cannot_be_overruled(self):
        pid = self.new_playset(["local:Big", "local:Needs"])
        st, err, _ = self.post(f"/api/playsets/{pid}/winner", {"pairs": [["local:Big", "local:Needs"]]})
        self.assertEqual(st, 400)
        self.assertIn("dependency", err["error"])

    def test_both_mods_must_be_in_the_playset(self):
        st, err, _ = self.post(f"/api/playsets/{self.pid}/winner", {"pairs": [["local:Big", "local:Needs"]]})
        self.assertEqual(st, 400)

    def test_reordering_by_hand_cancels_the_choice(self):
        self.post(f"/api/playsets/{self.pid}/winner", {"pairs": [["local:Big", "local:Small"]]})
        self.post(f"/api/playsets/{self.pid}/update", {"auto_sort": False})
        self.post(f"/api/playsets/{self.pid}/update", {"mods": ["local:Big", "local:Small"]})
        self.assertEqual(self.playset()["winners"], [])

    def test_forget_a_choice(self):
        self.post(f"/api/playsets/{self.pid}/winner", {"pairs": [["local:Big", "local:Small"]]})
        st, ps, _ = self.post(f"/api/playsets/{self.pid}/winner", {"pairs": [["local:Big", "local:Small"]], "forget": True})
        self.assertEqual(ps["winners"], [])
        self.assertEqual(ps["mods"], ["local:Small", "local:Big"])   # forgetting changes no order

    def test_bad_input_is_refused(self):
        for body in ({}, {"pairs": "x"}, {"pairs": [["a"]]}, {"pairs": [[1, 2]]}):
            self.assertEqual(self.post(f"/api/playsets/{self.pid}/winner", body)[0], 400, body)

    def test_the_opposite_choice_replaces_the_first(self):
        self.post(f"/api/playsets/{self.pid}/winner", {"pairs": [["local:Big", "local:Small"]]})
        st, ps, _ = self.post(f"/api/playsets/{self.pid}/winner", {"pairs": [["local:Small", "local:Big"]]})
        self.assertEqual(ps["winners"], [["local:Small", "local:Big"]])
        self.assertEqual(ps["mods"], ["local:Big", "local:Small"])


if __name__ == "__main__":
    unittest.main()
