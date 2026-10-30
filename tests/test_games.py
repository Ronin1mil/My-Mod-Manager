import unittest

from modmanager import games


class Registry(unittest.TestCase):
    def test_supported_games_and_their_pinned_facts(self):
        self.assertEqual(list(games.GAMES), ["ck3", "eu5", "vic3", "bannerlord"])
        got = {g.id: (g.app_id, g.load_file, g.load_style, g.install_marker) for g in games.GAMES.values()}
        self.assertEqual(got, {
            "ck3": ("1158310", "dlc_load.json", "descriptor", ("game", "common")),
            "eu5": ("3450310", "dlc_load.json", "path", ("game", "in_game")),
            "vic3": ("529340", "content_load.json", "enabled_paths", ("game", "common")),
            "bannerlord": ("261550", "(command line)", "modules", ("Modules", "Native")),
        })

    def test_ids_are_url_safe_and_unique_and_app_ids_numeric(self):
        for g in games.GAMES.values():
            self.assertRegex(g.id, r"^[a-z0-9]+$")
            self.assertTrue(g.app_id.isdigit())
            self.assertIn(g.load_style, ("descriptor", "path", "enabled_paths", "modules"))
        self.assertEqual(len({g.app_id for g in games.GAMES.values()}), len(games.GAMES))

    def test_every_game_has_a_complete_theme(self):
        need = {"--bg", "--side", "--panel", "--line", "--ink", "--mut", "--acc", "--accink", "--p1", "--p2", "--p3"}
        for g in games.GAMES.values():
            self.assertEqual(need - set(g.theme), set(), g.id)
            for v in g.theme.values():
                self.assertRegex(v, r"^#[0-9a-fA-F]{6}$")

    def test_public_view_has_no_paths_and_nothing_unexpected(self):
        p = games.CK3.public()
        self.assertEqual(set(p), {"id", "name", "app_id", "load_file", "theme", "verified", "install_marker", "kind",
                                  "has_conflicts", "has_saves", "custom"})
        self.assertEqual(p["install_marker"], "game/common")

    def test_only_games_checked_on_a_real_install_are_marked_verified(self):
        # Play confirmed loading the playset's mods (docs/22-checked-on-a-real-pc.md)
        self.assertEqual([g.id for g in games.GAMES.values() if g.verified], ["ck3", "eu5"])

    def test_bannerlord_new_playsets_start_with_the_official_modules_in_dependency_order(self):
        # dependencies read from the SubModule.xml files of a real 1.5.6 install
        self.assertEqual(games.BANNERLORD.seed_mods,
                         ("Native", "SandBoxCore", "BirthAndDeath", "CustomBattle", "Sandbox", "StoryMode", "NavalDLC"))

    def test_get_unknown_game(self):
        with self.assertRaises(ValueError):
            games.get("hoi4")
        self.assertIs(games.get("eu5"), games.EU5)


if __name__ == "__main__":
    unittest.main()
