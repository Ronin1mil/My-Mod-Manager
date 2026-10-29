import unittest

from modmanager import games


class Registry(unittest.TestCase):
    def test_supported_games_and_their_pinned_facts(self):
        self.assertEqual(list(games.GAMES), ["ck3", "eu5", "vic3"])
        got = {g.id: (g.app_id, g.load_file, g.load_style, g.install_marker) for g in games.GAMES.values()}
        self.assertEqual(got, {
            "ck3": ("1158310", "dlc_load.json", "descriptor", ("game", "common")),
            "eu5": ("3450310", "dlc_load.json", "path", ("game", "in_game")),
            "vic3": ("529340", "content_load.json", "descriptor", ("game", "common")),
        })

    def test_ids_are_url_safe_and_unique_and_app_ids_numeric(self):
        for g in games.GAMES.values():
            self.assertRegex(g.id, r"^[a-z0-9]+$")
            self.assertTrue(g.app_id.isdigit())
            self.assertIn(g.load_style, ("descriptor", "path"))
        self.assertEqual(len({g.app_id for g in games.GAMES.values()}), 3)

    def test_every_game_has_a_complete_theme(self):
        need = {"--bg", "--side", "--panel", "--line", "--ink", "--mut", "--acc", "--accink", "--p1", "--p2", "--p3"}
        for g in games.GAMES.values():
            self.assertEqual(need - set(g.theme), set(), g.id)
            for v in g.theme.values():
                self.assertRegex(v, r"^#[0-9a-fA-F]{6}$")

    def test_public_view_has_no_paths_and_nothing_unexpected(self):
        p = games.CK3.public()
        self.assertEqual(set(p), {"id", "name", "app_id", "load_file", "theme", "verified", "install_marker"})
        self.assertEqual(p["install_marker"], "game/common")

    def test_nothing_is_marked_verified_until_checked_on_a_real_install(self):
        self.assertFalse(any(g.verified for g in games.GAMES.values()))

    def test_get_unknown_game(self):
        with self.assertRaises(ValueError):
            games.get("hoi4")
        self.assertIs(games.get("eu5"), games.EU5)


if __name__ == "__main__":
    unittest.main()
