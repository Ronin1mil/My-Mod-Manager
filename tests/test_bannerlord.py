"""Mount & Blade II: Bannerlord: modules (SubModule.xml), dependency order, launching with a module list, and the
launcher's saved selection. Built on a fake install; nothing here has run against a real game."""
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from modmanager import detect, games, launcherdb, order, paths, scan
from tests.helpers import GameCase

BL = games.BANNERLORD


def submodule(mid, name=None, version="v1.0.0", official=False, deps=(), optional=(), after=(), incompatible=(), meta=(), extra=""):
    parts = [f'<Id value="{mid}"/>', f'<Name value="{name or mid}"/>', f'<Version value="{version}"/>']
    if official:
        parts.append('<Official value="true"/>')
    if deps or optional:
        parts.append("<DependedModules>" + "".join(f'<DependedModule Id="{d}"/>' for d in deps)
                     + "".join(f'<DependedModule Id="{d}" Optional="true"/>' for d in optional) + "</DependedModules>")
    if meta:
        parts.append("<DependedModuleMetadatas>" + "".join(meta) + "</DependedModuleMetadatas>")
    if after:
        parts.append("<ModulesToLoadAfterThis>" + "".join(f'<Module Id="{a}"/>' for a in after) + "</ModulesToLoadAfterThis>")
    if incompatible:
        parts.append("<IncompatibleModules>" + "".join(f'<Module Id="{i}"/>' for i in incompatible) + "</IncompatibleModules>")
    parts.append(extra)
    return '<?xml version="1.0" encoding="utf-8"?>\n<Module>' + "".join(parts) + "</Module>"


def install(root, workshop=None):
    """A fake Bannerlord install + workshop folder."""
    def put(base, folder, xml):
        (base / folder).mkdir(parents=True, exist_ok=True)
        (base / folder / "SubModule.xml").write_text(xml, encoding="utf-8")
    m = Path(root) / "Modules"
    put(m, "Native", submodule("Native", version="v1.2.9.12345", official=True))
    put(m, "SandBoxCore", submodule("SandBoxCore", official=True, deps=["Native"]))
    put(m, "CustomBattle", submodule("CustomBattle", official=True, deps=["Native", "SandBoxCore"]))
    put(m, "Sandbox", submodule("Sandbox", official=True, deps=["Native", "SandBoxCore"]))
    put(m, "StoryMode", submodule("StoryMode", official=True, deps=["Native", "SandBoxCore", "Sandbox"]))
    put(m, "Bannerlord.Harmony", submodule("Bannerlord.Harmony", "Harmony", deps=["Native"]))
    put(m, "Bannerlord.ButterLib", submodule("Bannerlord.ButterLib", "ButterLib", deps=["Bannerlord.Harmony"]))
    put(m, "MyMod", submodule("MyMod", "My Mod", deps=["Native", "SandBoxCore", "Bannerlord.Harmony"], optional=["Bannerlord.ButterLib"],
                              after=["LateMod"]))
    put(m, "LateMod", submodule("LateMod", "Late Mod", deps=["Native"]))
    if workshop:
        put(Path(workshop), "3000001", submodule("WorkshopMod", "Workshop Mod", deps=["Native"]))
        put(Path(workshop), "3000002", submodule("MyMod", "My Mod (workshop copy)"))  # same id as a Modules one: first copy wins
    return Path(root)


class Parsing(unittest.TestCase):
    def test_every_kind_of_rule(self):
        xml = submodule("A", deps=["Native"], optional=["Soft"], after=["Later"], incompatible=["Bad"], meta=[
            '<DependedModuleMetadata id="Before" order="LoadBeforeThis" version="v1.0.0"/>',
            '<DependedModuleMetadata id="Opt" order="LoadBeforeThis" optional="true"/>',
            '<DependedModuleMetadata id="After" order="LoadAfterThis"/>',
            '<DependedModuleMetadata id="Clash" incompatible="true"/>'])
        s = scan.parse_submodule(xml)
        self.assertEqual(s["dependencies"], ["Native", "Before"])
        self.assertEqual(s["load_after"], ["Soft", "Opt"])           # soft: only if present
        self.assertEqual(s["load_before"], ["After", "Later"])       # others load after this one
        self.assertEqual(s["incompatible"], ["Clash", "Bad"])
        self.assertFalse(s["official"])
        self.assertTrue(scan.parse_submodule(submodule("Native", official=True))["official"])
        self.assertTrue(scan.parse_submodule(submodule("StoryMode"))["official"])  # by id too

    def test_hostile_or_broken_files_are_refused(self):
        for bad in ("", "not xml", "<Other/>", "<Module/>", submodule("a b"), submodule("x*y"), submodule("../../etc"),
                    '<!DOCTYPE m [<!ENTITY e "x">]><Module><Id value="E"/></Module>', "<Module>" + "x" * (2 * 1024 * 1024)):
            self.assertIsNone(scan.parse_submodule(bad), bad[:40])


class Scanning(unittest.TestCase):
    def setUp(self):
        t = tempfile.TemporaryDirectory()
        self.addCleanup(t.cleanup)
        self.r = Path(t.name)
        self.root = install(self.r / "game", self.r / "ws")
        self.mods = scan.scan_modules(self.root, self.r / "ws")

    def test_modules_and_workshop_items_are_found_with_the_games_precedence(self):
        self.assertEqual(set(self.mods), {"local:Native", "local:SandBoxCore", "local:CustomBattle", "local:Sandbox", "local:StoryMode",
                                          "local:Bannerlord.Harmony", "local:Bannerlord.ButterLib", "local:MyMod", "local:LateMod",
                                          "ws:3000001"})  # the workshop copy of MyMod loses
        self.assertEqual(self.mods["ws:3000001"]["meta_id"], "WorkshopMod")
        self.assertEqual(self.mods["ws:3000001"]["remote_id"], "3000001")
        self.assertEqual(self.mods["local:MyMod"]["name"], "My Mod")

    def test_official_modules_rank_first_and_are_flagged(self):
        self.assertEqual({k for k, m in self.mods.items() if m["official"]}, {"local:Native", "local:SandBoxCore", "local:CustomBattle", "local:Sandbox", "local:StoryMode"})
        self.assertEqual(self.mods["local:Native"]["rank"], 0)
        self.assertEqual(self.mods["local:MyMod"]["rank"], 1)

    def test_game_version_comes_from_the_native_module(self):
        self.assertEqual(paths.game_version(self.root, BL), "1.2.9")
        self.assertEqual(paths.game_version(self.r / "nowhere", BL), "")

    def test_the_install_is_recognised_from_any_path_inside_it(self):
        for p in (self.root, self.root / "Modules", self.root / "Modules/Native", self.root / "Modules/MyMod/bin"):
            self.assertEqual(detect.find_install_root(p, BL), self.root, str(p))
        self.assertIsNone(detect.find_install_root(self.r / "ws", BL))

    def test_unreadable_module_folders_are_skipped(self):
        real = Path.is_dir

        def is_dir(self_):
            if self_.name == "MyMod":
                raise OSError(448, "untrusted mount point")
            return real(self_)
        with mock.patch.object(Path, "is_dir", is_dir):
            mods = scan.scan_modules(self.root, self.r / "ws")
        self.assertNotIn("local:MyMod", mods)
        self.assertIn("local:Native", mods)


class Ordering(unittest.TestCase):
    def setUp(self):
        t = tempfile.TemporaryDirectory()
        self.addCleanup(t.cleanup)
        self.mods = scan.scan_modules(install(Path(t.name) / "game"), None)
        self.L = lambda *n: [f"local:{x}" for x in n]

    def sorted(self, *names):
        return [m.split(":")[1] for m in order.compute_order(self.mods, self.L(*names), True)["order"]]

    def test_official_first_dependencies_before_dependents(self):
        out = self.sorted("MyMod", "Bannerlord.ButterLib", "Bannerlord.Harmony", "StoryMode", "Sandbox", "SandBoxCore", "Native")
        self.assertEqual(out[:5], ["Native", "SandBoxCore", "Sandbox", "StoryMode", "Bannerlord.Harmony"])
        self.assertLess(out.index("Bannerlord.Harmony"), out.index("Bannerlord.ButterLib"))
        self.assertLess(out.index("Bannerlord.ButterLib"), out.index("MyMod"))  # MyMod's optional dependency: before it when present

    def test_an_optional_dependency_is_not_needed_and_not_a_warning(self):
        res = order.compute_order(self.mods, self.L("Native", "SandBoxCore", "Bannerlord.Harmony", "MyMod"), True)
        self.assertEqual([i for i in res["issues"] if i["severity"] == "error"], [])

    def test_modules_to_load_after_this(self):
        out = self.sorted("LateMod", "MyMod", "Native", "SandBoxCore", "Bannerlord.Harmony")
        self.assertLess(out.index("MyMod"), out.index("LateMod"))

    def test_missing_and_disabled_dependencies_are_errors_with_the_fix(self):
        res = order.compute_order(self.mods, self.L("Native", "Bannerlord.ButterLib"), True)
        codes = {(i["code"], i["module"]) for i in res["issues"]}
        self.assertIn(("disabled_dependency", "local:Bannerlord.ButterLib"), codes)  # Harmony is installed, just not in the playset
        fix = next(i["fix"] for i in res["issues"] if i["code"] == "disabled_dependency")
        self.assertEqual(fix, {"kind": "enable", "id": "local:Bannerlord.Harmony"})

    def test_the_other_games_are_unaffected_by_rank(self):
        mods = {"a": {"id": "a", "name": "A", "dependencies": [], "exists": True, "supported_version": ""},
                "b": {"id": "b", "name": "B", "dependencies": [], "exists": True, "supported_version": ""}}
        self.assertEqual(order.compute_order(mods, ["b", "a"], True)["order"], ["b", "a"])  # the user's order stays


class Playing(GameCase):
    GAME = BL

    def kw(self, g):
        base = super().kw(g)
        if g is BL:
            self.root = install(self.r / "bl-install", self.ws(g))
            base["game_dir"] = self.root
            base["game_version_"] = None  # read it from the Native module like the real app
        return base

    def app(self):
        return self.hub.app("bannerlord")

    def test_state_says_what_this_game_does_not_have(self):
        s = self.req("GET", "/api/state")[1]
        self.assertEqual((s["game"]["kind"], s["game"]["has_conflicts"], s["game"]["has_saves"]), ("modules", False, False))
        self.assertEqual(s["game_version"], "1.2.9")
        self.assertEqual(len(s["mods"]), 10)

    def test_a_new_playset_starts_with_the_official_modules_in_order(self):
        pid = self.post("/api/playsets", {"name": "New"})[1]["id"]
        ps = next(p for p in self.req("GET", "/api/state")[1]["playsets"] if p["id"] == pid)
        self.assertEqual(ps["mods"], ["local:Native", "local:SandBoxCore", "local:CustomBattle", "local:Sandbox", "local:StoryMode"])
        pid2 = self.post("/api/playsets", {"name": "Asked", "mods": ["local:Native"]})[1]["id"]  # what was asked for wins
        self.assertEqual(next(p for p in self.req("GET", "/api/state")[1]["playsets"] if p["id"] == pid2)["mods"], ["local:Native"])

    def test_conflicts_are_empty_not_an_error(self):
        pid = self.post("/api/playsets", {"name": "P"})[1]["id"]
        a = self.req("GET", f"/api/analyse/{pid}")[1]
        self.assertEqual((a["conflicts"], a["pending"]), ([], False))
        self.assertEqual(self.req("GET", f"/api/conflicts/{pid}")[1]["conflicts"], [])

    def test_play_starts_the_game_with_the_module_list_in_order(self):
        pid = self.post("/api/playsets", {"name": "P", "mods": self.L("Native", "SandBoxCore", "Bannerlord.Harmony", "MyMod")})[1]["id"]
        self.post(f"/api/playsets/{pid}/update", {"launch_args": ["-debug_mode"]})
        exe = self.root / "bin/Win64_Shipping_Client/Bannerlord.exe"
        exe.parent.mkdir(parents=True)
        exe.write_bytes(b"")
        with mock.patch("modmanager.launch.subprocess.Popen") as popen:
            st, res, _ = self.post(f"/api/playsets/{pid}/launch")
        self.assertEqual(st, 200, res)
        args = popen.call_args[0][0]
        self.assertEqual(args, [str(exe), "/singleplayer", "_MODULES_*Native*SandBoxCore*Bannerlord.Harmony*MyMod*_MODULES_", "-debug_mode"])
        self.assertEqual(popen.call_args[1]["cwd"], str(exe.parent))
        self.assertEqual((res["via"], res["written"], res["modules"]), ("exe", 4, ["Native", "SandBoxCore", "Bannerlord.Harmony", "MyMod"]))
        # the Paradox load file is not written for this game
        self.assertFalse(list(self.user().glob("*load*.json")))

    def test_a_disabled_module_is_left_out_and_a_partial_launch_uses_the_subset(self):
        pid = self.post("/api/playsets", {"name": "P", "mods": self.L("Native", "SandBoxCore", "Bannerlord.Harmony", "MyMod")})[1]["id"]
        self.post(f"/api/playsets/{pid}/update", {"disabled": ["local:Bannerlord.Harmony"]})
        exe = self.root / "bin/Win64_Shipping_Client/Bannerlord.exe"
        exe.parent.mkdir(parents=True)
        exe.write_bytes(b"")
        with mock.patch("modmanager.launch.subprocess.Popen") as popen:
            self.post(f"/api/playsets/{pid}/launch")
            self.assertIn("_MODULES_*Native*SandBoxCore*MyMod*_MODULES_", popen.call_args[0][0])
            res = self.post(f"/api/playsets/{pid}/launch", {"only": ["local:Native", "local:SandBoxCore"]})[1]
            self.assertIn("_MODULES_*Native*SandBoxCore*_MODULES_", popen.call_args[0][0])
        self.assertTrue(res["partial"])

    def test_a_missing_executable_is_explained(self):
        pid = self.post("/api/playsets", {"name": "P"})[1]["id"]
        st, res, _ = self.post(f"/api/playsets/{pid}/launch")
        self.assertEqual(st, 400)
        self.assertIn("Bannerlord", res["error"])

    L = staticmethod(lambda *n: [f"local:{x}" for x in n])


class LauncherSelection(GameCase):
    GAME = BL

    XML = """<?xml version="1.0" encoding="utf-8"?>
<UserData xmlns:xsd="http://www.w3.org/2001/XMLSchema" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
  <GameType>Singleplayer</GameType>
  <SingleplayerData><ModDatas>
    <UserModData><Id>Native</Id><LastKnownVersion>v1.2.9.1</LastKnownVersion><IsSelected>true</IsSelected></UserModData>
    <UserModData><Id>SandBoxCore</Id><LastKnownVersion>v1.2.9.1</LastKnownVersion><IsSelected>true</IsSelected></UserModData>
    <UserModData><Id>Bannerlord.Harmony</Id><LastKnownVersion>v2.0.0</LastKnownVersion><IsSelected>false</IsSelected></UserModData>
    <UserModData><Id>NotInstalled</Id><LastKnownVersion>v1.0.0</LastKnownVersion><IsSelected>true</IsSelected></UserModData>
  </ModDatas></SingleplayerData>
  <MultiplayerData><ModDatas><UserModData><Id>Native</Id><IsSelected>true</IsSelected></UserModData></ModDatas></MultiplayerData>
</UserData>"""

    def kw(self, g):
        base = super().kw(g)
        if g is BL:
            base["game_dir"] = install(self.r / "bl-install", self.ws(g))
            (self.user(g) / "Configs").mkdir(parents=True, exist_ok=True)
            (self.user(g) / "Configs/LauncherData.xml").write_text(self.XML, encoding="utf-8")
        return base

    def test_the_launchers_selection_becomes_a_playset(self):
        info = self.req("GET", "/api/launcher")[1]
        self.assertTrue(info["found"])
        self.assertEqual([(p["name"], p["mods"]) for p in info["playsets"]], [("Launcher selection", 4)])
        res = self.post("/api/launcher/import", {})[1]
        self.assertEqual([i["name"] for i in res["imported"]], ["Launcher selection"])
        ps = self.req("GET", "/api/state")[1]["playsets"][0]
        self.assertEqual(ps["mods"], ["local:Native", "local:SandBoxCore", "local:Bannerlord.Harmony"])
        self.assertEqual(ps["disabled"], ["local:Bannerlord.Harmony"])   # IsSelected=false -> kept but off
        self.assertEqual(res["lost"], ["Launcher selection: NotInstalled"])  # not installed: reported, not invented

    def test_no_file_and_a_damaged_file(self):
        self.hub.app("bannerlord")
        (self.user() / "Configs/LauncherData.xml").write_text("<UserData><oops", encoding="utf-8")
        info = self.req("GET", "/api/launcher")[1]
        self.assertTrue(info["error"])
        (self.user() / "Configs/LauncherData.xml").unlink()
        self.assertFalse(self.req("GET", "/api/launcher")[1]["found"])

    def test_the_reader_alone(self):
        self.assertEqual(launcherdb.read_bannerlord(None), [])
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / "Configs").mkdir()
            (Path(d) / "Configs/LauncherData.xml").write_text('<!DOCTYPE x [<!ENTITY e "x">]><UserData/>', encoding="utf-8")
            with self.assertRaises(ValueError):
                launcherdb.read_bannerlord(d)


if __name__ == "__main__":
    unittest.main()


class Installing(unittest.TestCase):
    def setUp(self):
        t = tempfile.TemporaryDirectory()
        self.addCleanup(t.cleanup)
        self.r = Path(t.name)
        self.root = install(self.r / "game")
        self.cfg = self.r / "cfg"

    def zip(self, files, name="mod.zip"):
        import zipfile
        p = self.r / name
        with zipfile.ZipFile(p, "w") as z:
            for k, v in files.items():
                z.writestr(k, v)
        return p

    def test_a_module_is_installed_into_modules_and_found_by_the_scan(self):
        from modmanager import install as inst
        z = self.zip({"Modules/NewMod/SubModule.xml": submodule("NewMod", "New Mod", deps=["Native"]), "Modules/NewMod/ModuleData/a.xml": "<a/>"})
        rep = inst.install_modules_archive(z, self.root, "mod.zip", self.cfg)
        self.assertEqual(rep["installed"], [{"folder": "NewMod", "name": "New Mod", "upgraded": False, "id": "local:NewMod"}])
        self.assertTrue((self.root / "Modules/NewMod/ModuleData/a.xml").is_file())
        self.assertIn("local:NewMod", scan.scan_modules(self.root))

    def test_an_upgrade_backs_up_the_old_copy(self):
        from modmanager import install as inst
        z = self.zip({"Harmony/SubModule.xml": submodule("Bannerlord.Harmony", "Harmony 2", version="v2.0.0")})
        rep = inst.install_modules_archive(z, self.root, "x.zip", self.cfg)
        self.assertTrue(rep["installed"][0]["upgraded"])
        self.assertEqual(scan.scan_modules(self.root)["local:Bannerlord.Harmony"]["name"], "Harmony 2")
        self.assertTrue(any((self.cfg / "backups").iterdir()))

    def test_official_modules_are_never_replaced_and_junk_is_refused(self):
        from modmanager import install as inst
        z = self.zip({"Native/SubModule.xml": submodule("Native", "Fake Native", official=True)})
        with self.assertRaises(ValueError):
            inst.install_modules_archive(z, self.root, "n.zip", self.cfg)
        self.assertEqual(scan.scan_modules(self.root)["local:Native"]["name"], "Native")
        with self.assertRaises(ValueError):
            inst.install_modules_archive(self.zip({"readme.txt": "hi"}, "j.zip"), self.root, "j.zip", self.cfg)
        with self.assertRaises(ValueError):  # an id that could not be put on a command line
            inst.install_modules_archive(self.zip({"x/SubModule.xml": submodule("a*b")}, "k.zip"), self.root, "k.zip", self.cfg)
        with self.assertRaises(ValueError):  # path tricks stay inside the archive's own folder
            inst.install_modules_archive(self.zip({"../../evil/SubModule.xml": submodule("Evil")}, "e.zip"), self.root, "e.zip", self.cfg)
        self.assertFalse((self.r / "evil").exists())

    def test_uninstall_moves_to_backup_and_refuses_official(self):
        from modmanager import install as inst
        mods = scan.scan_modules(self.root)
        where = inst.uninstall_module(self.root, mods["local:LateMod"], self.cfg)
        self.assertTrue(Path(where).is_dir())
        self.assertFalse((self.root / "Modules/LateMod").exists())
        with self.assertRaises(ValueError):
            inst.uninstall_module(self.root, mods["local:Native"], self.cfg)
