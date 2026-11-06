"""Europa Universalis IV, Hearts of Iron IV, Stellaris and Imperator: Rome (built in since 1.2.0, unverified).

Their layout comes from Irony Mod Manager's game registrations: EU4, HOI4 and Stellaris keep their content straight in
the install folder and their launcher-settings.json at the install root; Imperator keeps both like CK3 (game/, launcher/).
All four read mod/*.mod descriptors and take the enabled mods from dlc_load.json."""
import json
import tempfile
import unittest
from pathlib import Path

from modmanager import detect, games
from modmanager.paths import game_version, launcher_exe
from tests.helpers import GameCase, mkinstall, mkmod

NEW = (games.EU4, games.HOI4, games.STELLARIS, games.IMPERATOR)


class Registry(unittest.TestCase):
    def test_the_four_are_unverified_paradox_games_with_descriptor_load_files(self):
        for g in NEW:
            self.assertEqual((g.kind, g.load_file, g.load_style, g.verified), ("paradox", "dlc_load.json", "descriptor", False), g.id)
            self.assertTrue(g.has_conflicts and g.has_saves)

    def test_root_content_games_compare_only_their_script_folders_with_the_base_game(self):
        for g in (games.EU4, games.HOI4, games.STELLARIS):
            self.assertEqual(g.vanilla_dir_name, "")
            self.assertIn("common", g.vanilla_only)
            self.assertNotIn("", g.vanilla_only)
        self.assertEqual((games.IMPERATOR.vanilla_dir_name, games.IMPERATOR.vanilla_only), ("game", ()))


class LauncherSettingsAtTheRoot(unittest.TestCase):
    def setUp(self):
        t = tempfile.TemporaryDirectory()
        self.addCleanup(t.cleanup)
        self.root = Path(t.name) / "Europa Universalis IV"
        (self.root / "missions").mkdir(parents=True)
        (self.root / "eu4.exe").write_bytes(b"")

    def write(self, rel, d):
        (self.root / rel).parent.mkdir(parents=True, exist_ok=True)
        (self.root / rel).write_text(json.dumps(d))

    def test_exe_and_version_from_a_root_launcher_settings_file(self):
        self.write("launcher-settings.json", {"rawVersion": "1.37.5.0", "exePath": "eu4.exe", "exeArgs": ["-debug_mode", "; bad"]})
        exe, args = launcher_exe(self.root)
        self.assertEqual((exe, args), ((self.root / "eu4.exe").resolve(), ["-debug_mode"]))
        self.assertEqual(game_version(self.root, games.EU4), "1.37.5.0")

    def test_the_launcher_folder_wins_when_both_exist(self):
        (self.root / "binaries").mkdir()
        (self.root / "binaries/new.exe").write_bytes(b"")
        self.write("launcher-settings.json", {"exePath": "eu4.exe"})
        self.write("launcher/launcher-settings.json", {"exePath": "../binaries/new.exe"})
        self.assertEqual(launcher_exe(self.root)[0], (self.root / "binaries/new.exe").resolve())

    def test_an_exe_outside_the_install_or_missing_is_refused(self):
        self.write("launcher-settings.json", {"exePath": "../evil.exe"})
        (self.root.parent / "evil.exe").write_bytes(b"")
        self.assertEqual(launcher_exe(self.root), (None, []))
        self.write("launcher-settings.json", {"exePath": "gone.exe"})
        self.assertEqual(launcher_exe(self.root), (None, []))


class Detection(unittest.TestCase):
    def test_each_is_found_in_a_steam_library_and_not_mistaken_for_another(self):
        with tempfile.TemporaryDirectory() as t:
            for g in NEW:
                lib = Path(t) / g.id
                mkinstall(lib, g)
                self.assertEqual(len(detect.detect_all(g, [lib])), 1, g.id)
                for other in NEW + (games.CK3,):
                    if other is not g:
                        self.assertEqual(detect.detect_all(other, [lib]), [], (g.id, other.id))


class Eu4Flow(GameCase):
    GAME = games.EU4

    def test_play_writes_dlc_load_with_mod_descriptors_in_order(self):
        mkmod(self.user(), "lib", "Lib")
        mkmod(self.user(), "big", "Big", deps=["Lib"])
        pid = self.new_playset(["local:lib", "local:big"])
        st, res, _ = self.post(f"/api/playsets/{pid}/launch")
        self.assertEqual(st, 200, res)
        dlc = json.loads((self.user() / "dlc_load.json").read_text())
        self.assertEqual(dlc["enabled_mods"], ["mod/lib.mod", "mod/big.mod"])

    def test_base_game_files_in_the_install_folder_itself_are_compared(self):
        root = mkinstall(self.r / "Lib", self.GAME, files={"common/ideas/base.txt": "my_idea = { }",
                                                           "binaries/notes.txt": "my_idea = { }"})
        self.assertTrue((root / "common/ideas/base.txt").is_file())   # straight in the install folder, no game/
        mkmod(self.user(), "M", files={"common/ideas/m.txt": "my_idea = { }"})
        self.post("/api/paths", {"game_dir": str(root), "include_vanilla": True})
        pid = self.new_playset(["local:M"])
        an = self.req("GET", f"/api/analyse/{pid}")[1]
        self.assertEqual([c.get("vanilla") for c in an["conflicts"]], [True])


if __name__ == "__main__":
    unittest.main()
