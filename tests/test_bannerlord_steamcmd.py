"""steamcmd downloads for Bannerlord: the game only loads modules from its Modules folder (or Steam's own subscriptions),
so each downloaded item is copied there, marked with its Workshop id, and playsets that list the item use that copy."""
import os
import subprocess
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

from modmanager import games, install, scan, workshop
from modmanager.library import Library
from modmanager.server import GameApp
from modmanager.store import Store
from tests.test_bannerlord import install as fake_install, submodule

BL = games.BANNERLORD


class Base(unittest.TestCase):
    def setUp(self):
        self.t = tempfile.TemporaryDirectory()
        self.addCleanup(self.t.cleanup)
        self.r = Path(self.t.name)
        p = mock.patch.dict(os.environ, {"MODMANAGER_CONFIG_DIR": str(self.r / "cfg")})
        p.start()
        self.addCleanup(p.stop)
        self.root = fake_install(self.r / "game")
        self.ws = self.r / "ws"
        self.ws.mkdir()
        self.exe = self.r / "steamcmd" / "steamcmd.exe"
        self.exe.parent.mkdir()
        self.exe.write_text("")
        self.content = workshop.content_dir(self.exe, BL)

    def downloaded(self, wid, mid, version="v1.0.0"):
        d = self.content / wid
        d.mkdir(parents=True, exist_ok=True)
        (d / "SubModule.xml").write_text(submodule(mid, mid + " name", version=version, deps=["Native"]), encoding="utf-8")
        (d / "bin").mkdir(exist_ok=True)
        (d / "bin" / "x.dll").write_text(version)
        return d


class InstallFolder(Base):
    def test_copied_into_modules_marked_and_found_with_its_workshop_id(self):
        src = self.downloaded("3001", "NewMod")
        rep = install.install_module_folder(src, self.root, "3001", self.r / "cfg")
        self.assertEqual(rep, {"folder": "NewMod", "name": "NewMod name", "upgraded": False, "id": "local:NewMod"})
        self.assertTrue((self.root / "Modules/NewMod/bin/x.dll").is_file())
        self.assertTrue(src.is_dir(), "steamcmd keeps its own copy (its cache for the next update)")
        m = scan.scan_modules(self.root, self.ws)["local:NewMod"]
        self.assertEqual((m["source"], m["remote_id"]), ("local", "3001"))

    def test_an_existing_copy_goes_to_the_backup_folder(self):
        install.install_module_folder(self.downloaded("3001", "NewMod", "v1.0.0"), self.root, "3001", self.r / "cfg")
        rep = install.install_module_folder(self.downloaded("3001", "NewMod", "v2.0.0"), self.root, "3001", self.r / "cfg")
        self.assertTrue(rep["upgraded"])
        self.assertEqual((self.root / "Modules/NewMod/bin/x.dll").read_text(), "v2.0.0")
        backups = list((self.r / "cfg" / "backups").glob("NewMod-*"))
        self.assertEqual(len(backups), 1)
        self.assertEqual((backups[0] / "bin/x.dll").read_text(), "v1.0.0")

    def test_official_modules_and_non_modules_are_refused(self):
        d = self.content / "9"
        d.mkdir(parents=True)
        with self.assertRaises(ValueError):
            install.install_module_folder(d, self.root, "9")
        (d / "SubModule.xml").write_text(submodule("Native", official=True))
        with self.assertRaises(ValueError):
            install.install_module_folder(d, self.root, "9")
        self.assertIn("Native", (self.root / "Modules/Native/SubModule.xml").read_text())

    def test_a_bad_mark_is_ignored(self):
        install.install_module_folder(self.downloaded("3001", "NewMod"), self.root, "3001")
        (self.root / "Modules/NewMod" / install.WORKSHOP_MARK).write_text("../../etc")
        self.assertIsNone(scan.scan_modules(self.root, self.ws)["local:NewMod"]["remote_id"])


class DownloadAndUse(Base):
    def app(self):
        a = GameApp(BL, game_dir=str(self.root), workshop_dir=str(self.ws), user_dir=str(self.r / "docs"),
                    store=Store(self.r / "p.json", game=BL), library=Library(self.r / "l.json", game=BL), autodetect=False)
        a.store.update_settings(steamcmd=str(self.exe), steam_user="acct")
        return a

    def run_job(self, a, ids, fail=()):
        def fake(argv, **kw):
            wid = argv[argv.index("+workshop_download_item") + 2]
            if wid in fail:
                return subprocess.CompletedProcess(argv, 8, "ERROR! Download item failed (Failure).\n", "")
            self.downloaded(wid, f"Mod{wid}")
            return subprocess.CompletedProcess(argv, 0, f"Success. Downloaded item {wid}\n", "")
        a.downloads.runner = fake
        jid = a.download(ids, "steamcmd")["job"]["id"]
        end = time.time() + 5
        while time.time() < end:
            job = [j for j in a.downloads.status() if j["id"] == jid][0]
            if job["state"] in ("done", "failed"):
                return job
            time.sleep(0.01)
        self.fail("download did not finish")

    def test_playsets_use_the_installed_copies_in_the_same_place(self):
        a = self.app()
        pid = a.store.create("Pack", ["local:Native", "ws:4001", "local:LateMod", "ws:4002", "ws:4003"], disabled=["ws:4002"])
        job = self.run_job(a, ["4001", "4002", "4003"], fail={"4003"})
        self.assertEqual(job["items"]["4001"]["installed"], "Mod4001")
        ps = a.store.get(pid)
        self.assertEqual(ps["mods"], ["local:Native", "local:Mod4001", "local:LateMod", "local:Mod4002", "ws:4003"])
        self.assertEqual(ps["disabled"], ["local:Mod4002"])
        self.assertIn("local:Mod4001", a.mods)
        self.assertEqual(a.mods["local:Mod4001"]["remote_id"], "4001")

    def test_an_install_problem_fails_that_item_with_the_reason(self):
        a = self.app()
        a.game_root = None
        job = self.run_job(a, ["4001"])
        self.assertEqual(job["items"]["4001"]["state"], "failed")
        self.assertIn("not installed", job["items"]["4001"]["message"])
        self.assertIn("Modules folder", job["items"]["4001"]["message"])

    def test_a_playset_that_already_has_the_copy_keeps_one_entry(self):
        a = self.app()
        install.install_module_folder(self.downloaded("4001", "Mod4001"), self.root, "4001")
        a.rescan()
        pid = a.store.create("Both", ["ws:4001", "local:Mod4001"])
        self.run_job(a, ["4001"])
        self.assertEqual(a.store.get(pid)["mods"], ["local:Mod4001"])

    def test_other_games_leave_downloads_where_steamcmd_put_them(self):
        a = GameApp(games.CK3, user_dir=str(self.r / "ck3"), workshop_dir=str(self.ws), store=Store(self.r / "c.json", game=games.CK3),
                    library=Library(self.r / "cl.json", game=games.CK3), autodetect=False)
        a.store.update_settings(steamcmd=str(self.exe), steam_user="acct")
        with mock.patch.object(a.downloads, "start", return_value={"id": "1"}) as start:
            a.download(["5"], "steamcmd")
        self.assertIsNone(start.call_args.kwargs["after"])


if __name__ == "__main__":
    unittest.main()
