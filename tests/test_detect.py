"""Finding installs, Workshop folders, versions, logos and config folders - for every game."""
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from modmanager import detect, games, paths
from tests.helpers import ALL, mkinstall

PNG = b"\x89PNG\r\n\x1a\n" + b"0" * 20


class Detect(unittest.TestCase):
    def setUp(self):
        self.t = tempfile.TemporaryDirectory()
        self.r = Path(self.t.name)
        self.addCleanup(self.t.cleanup)

    def test_install_found_in_any_library_for_each_game(self):
        for g in ALL:
            lib = self.r / g.id / "SteamLibrary"
            root = mkinstall(lib, g, "1.7.6")
            found = detect.detect_all(g, [lib])
            self.assertEqual([f["path"] for f in found], [str(root)], g.id)
            self.assertEqual(found[0]["version"], "1.7.6")
            self.assertTrue(found[0]["workshop_dir"].replace("\\", "/").endswith(f"workshop/content/{g.app_id}"))

    def test_other_games_are_not_mistaken_for_this_one(self):
        lib = self.r / "Lib"
        mkinstall(lib, games.EU5)
        self.assertEqual(detect.detect_all(games.CK3, [lib]), [])
        self.assertEqual(len(detect.detect_all(games.EU5, [lib])), 1)

    def test_pasted_paths_resolve_to_the_install_root(self):
        for g in ALL:
            root = mkinstall(self.r / g.id, g)
            deep = root / "game" / g.install_marker[1] / "a" / "b" / "c"
            deep.mkdir(parents=True)
            for p in (root, root / "game", root / "game" / g.install_marker[1], deep):
                self.assertEqual(detect.find_install_root(p, g), root, (g.id, p))
            self.assertIsNone(detect.find_install_root(self.r / "nope", g))
            self.assertIsNone(detect.find_install_root("", g))
            self.assertIsNone(detect.find_install_root("   ", g))

    def test_renamed_install_folder_via_appmanifest(self):
        for g in ALL:
            lib = self.r / g.id / "Lib"
            (lib / "steamapps/common/Custom Name" / Path(*g.install_marker)).mkdir(parents=True)
            (lib / f"steamapps/appmanifest_{g.app_id}.acf").write_text('"AppState"\n{\n "installdir"\t\t"Custom Name"\n}')
            self.assertEqual([i["path"] for i in detect.detect_all(g, [lib])], [str(lib / "steamapps/common/Custom Name")])

    def test_no_game_means_empty_not_error(self):
        (self.r / "steamapps").mkdir()
        for g in ALL:
            self.assertEqual(detect.detect_all(g, [self.r]), [])

    def test_same_install_via_two_libraries_listed_once(self):
        lib = self.r / "Lib"
        mkinstall(lib, games.VIC3)
        self.assertEqual(len(detect.detect_all(games.VIC3, [lib, lib, Path(str(lib) + "/")])), 1)

    def test_vdf_with_windows_paths_and_several_libraries(self):
        vdf = '"libraryfolders"\n{\n\t"0"\n\t{\n\t\t"path"\t\t"C:\\\\Program Files (x86)\\\\Steam"\n\t}\n' \
              '\t"1"\n\t{\n\t\t"path"\t\t"G:\\\\SteamLibrary"\n\t}\n}'
        got = [str(p).replace("\\", "/") for p in paths.parse_library_folders_vdf(vdf)]
        self.assertEqual(got, ["C:/Program Files (x86)/Steam", "G:/SteamLibrary"])

    def test_libraries_from_libraryfolders_vdf_are_followed(self):
        steam, lib2 = self.r / "Steam", self.r / "Second"
        (steam / "steamapps").mkdir(parents=True)
        mkinstall(lib2, games.CK3)
        (steam / "steamapps/libraryfolders.vdf").write_text('"libraryfolders" { "1" { "path" "' + str(lib2).replace("\\", "\\\\") + '" } }')
        with mock.patch.object(paths, "steam_roots", return_value=[steam]):
            self.assertEqual(len(detect.detect_all(games.CK3, [])), 1)

    def test_version_file_variants(self):
        (self.r / "launcher").mkdir()
        f = self.r / "launcher/launcher-settings.json"
        for text, want in (('{"rawVersion": "v1.2.3 (abc)"}', "1.2.3"), ('{"version": "CK3 1.0"}', "1.0"),
                           ('{"rawVersion": "none"}', ""), ("garbage", ""), ("[]", ""), ('"x"', "")):
            f.write_text(text)
            self.assertEqual(paths.game_version(self.r), want, text)
        self.assertEqual(paths.game_version(None), "")
        self.assertEqual(paths.game_version(self.r / "missing"), "")

    def test_workshop_dir_only_for_steam_layout(self):
        root = mkinstall(self.r / "Lib", games.VIC3)
        self.assertIsNotNone(detect.workshop_dir_for(root, games.VIC3))
        manual = self.r / "Manual" / "Victoria 3"
        (manual / "game/common").mkdir(parents=True)
        self.assertIsNone(detect.workshop_dir_for(manual, games.VIC3))
        self.assertEqual(detect.describe(manual, games.VIC3)["store"], "manual")


class UserDirsAndConfig(unittest.TestCase):
    def test_user_dirs_use_each_games_folder_name(self):
        for g in ALL:
            self.assertTrue(any(p.name == g.user_dir_name and p.parent.name == "Paradox Interactive"
                                for p in paths.user_dirs(g)), g.id)

    def test_config_dir_is_per_game_and_overridable(self):
        with tempfile.TemporaryDirectory() as r:
            with mock.patch.dict(os.environ, {"MODMANAGER_CONFIG_DIR": r}):
                self.assertEqual(paths.config_dir(), Path(r))
                self.assertEqual(paths.config_dir(games.EU5), Path(r) / "eu5")
                self.assertTrue((Path(r) / "eu5").is_dir())

    def test_legacy_config_locations(self):
        with tempfile.TemporaryDirectory() as r, mock.patch.dict(os.environ, {"XDG_CONFIG_HOME": r}):
            names = {g.id: [p.parent.name for p in paths.legacy_config_files(g)] for g in ALL}
            self.assertEqual(names, {"ck3": ["ck3mm"], "eu5": ["eu5mm"], "vic3": ["vic3mm"]})


class Logos(unittest.TestCase):
    def setUp(self):
        self.t = tempfile.TemporaryDirectory()
        self.r = Path(self.t.name)
        p = mock.patch.dict(os.environ, {"MODMANAGER_CONFIG_DIR": str(self.r / "cfg")})
        p.start()
        self.addCleanup(p.stop)
        self.addCleanup(self.t.cleanup)
        nosteam = mock.patch.object(paths, "steam_roots", return_value=[])
        nosteam.start()
        self.addCleanup(nosteam.stop)

    def test_config_folder_logo_is_per_game(self):
        self.assertIsNone(paths.find_logo(games.CK3))
        (paths.config_dir(games.CK3) / "logo.png").write_bytes(b"x")
        self.assertEqual(paths.find_logo(games.CK3).name, "logo.png")
        self.assertIsNone(paths.find_logo(games.EU5))  # another game's logo is never used

    def test_explicit_logo_must_be_an_image_and_never_falls_back(self):
        (self.r / "evil.html").write_text("x")
        (paths.config_dir(games.CK3) / "logo.png").write_bytes(b"x")
        self.assertIsNone(paths.find_logo(games.CK3, self.r / "evil.html"))
        self.assertIsNone(paths.find_logo(games.CK3, self.r / "missing.png"))

    def test_oversized_logo_ignored(self):
        (paths.config_dir(games.CK3) / "logo.png").write_bytes(b"0" * (paths.MAX_LOGO + 1))
        self.assertIsNone(paths.find_logo(games.CK3))

    def test_steam_cache_uses_the_games_app_id(self):
        steam = self.r / "Steam"
        (steam / "appcache/librarycache").mkdir(parents=True)
        (steam / "appcache/librarycache/529340_logo.png").write_bytes(PNG)
        with mock.patch.object(paths, "steam_roots", return_value=[steam]):
            self.assertEqual(paths.find_logo(games.VIC3).name, "529340_logo.png")
            self.assertIsNone(paths.find_logo(games.CK3))

    def test_install_launcher_folder_logo(self):
        root = mkinstall(self.r / "Lib", games.EU5)
        (root / "launcher/eu5_logo.png").write_bytes(PNG)
        self.assertEqual(paths.find_logo(games.EU5, game_root=root).name, "eu5_logo.png")

    def test_fetch_logo_validation(self):
        for url in ("http://shared.fastly.steamstatic.com/x.png", "https://evil.example/logo.png",
                    "https://steamstatic.com.evil.example/x.png", "file:///etc/passwd"):
            with self.assertRaises(ValueError, msg=url):
                paths.fetch_logo(games.CK3, url)
        fake = mock.MagicMock()
        with mock.patch("urllib.request.urlopen", return_value=fake):
            fake.__enter__.return_value.read.return_value = b"<html>not a png</html>"
            with self.assertRaises(ValueError):
                paths.fetch_logo(games.CK3)
            fake.__enter__.return_value.read.return_value = PNG
            self.assertEqual(paths.fetch_logo(games.CK3).read_bytes(), PNG)
        self.assertEqual(paths.logo_url(games.EU5), "https://shared.fastly.steamstatic.com/store_item_assets/steam/apps/3450310/logo.png")


if __name__ == "__main__":
    unittest.main()
