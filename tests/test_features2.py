import io
import tarfile
import tempfile
import unittest
import zipfile
from pathlib import Path

from modmanager import games, install, scan
from modmanager.library import Library
from modmanager.server import GameApp
from modmanager.store import Store
from tests.test_core import mk


def make_tar(path, entries, mode="w:gz"):
    with tarfile.open(path, mode) as tf:
        for name, data in entries.items():
            if isinstance(data, tarfile.TarInfo):
                tf.addfile(data)
                continue
            ti = tarfile.TarInfo(name)
            ti.size = len(data)
            tf.addfile(ti, io.BytesIO(data))


class T(unittest.TestCase):
    def test_definition_conflict_names_the_file_per_mod(self):
        with tempfile.TemporaryDirectory() as r:
            mk(r, "A", {"common/goods/a_goods.txt": "g1 = { }"})
            mk(r, "B", {"common/goods/zz_b.txt": "g1 = { }"})
            c = scan.find_conflicts(scan.scan_mods(r), ["local:A", "local:B"])
            d = [x for x in c if x["kind"] == "definition"][0]
            self.assertEqual(d["files"], {"local:A": ["common/goods/a_goods.txt"], "local:B": ["common/goods/zz_b.txt"]})

    def test_tar_formats_install(self):
        for suffix, mode in ((".tar.gz", "w:gz"), (".tgz", "w:gz"), (".tar.bz2", "w:bz2"), (".tar.xz", "w:xz"), (".tar", "w")):
            with self.subTest(suffix=suffix), tempfile.TemporaryDirectory() as r:
                r = Path(r)
                a = r / f"My Mod{suffix}"
                make_tar(a, {"My Mod/.metadata/metadata.json": b'{"name": "My Mod", "version": "1"}', "My Mod/common/x.txt": b"x"}, mode)
                rep = install.install_archive(a, r / "user", a.name, r / "cfg")
                self.assertEqual(rep["installed"][0]["name"], "My Mod")
                self.assertTrue((r / "user/mod/My Mod/common/x.txt").is_file())

    def test_tar_rejects_unsafe_entries(self):
        link = tarfile.TarInfo("m/evil"); link.type = tarfile.SYMTYPE; link.linkname = "/etc/passwd"
        cases = {"traversal": {"../x.txt": b"x"}, "exe": {"m/.metadata/metadata.json": b"{}", "m/run.exe": b"MZ"}, "link": {"m/evil": link}}
        for name, entries in cases.items():
            with self.subTest(case=name), tempfile.TemporaryDirectory() as r:
                r = Path(r)
                make_tar(r / "a.tar.gz", entries)
                with self.assertRaises(ValueError):
                    install.install_archive(r / "a.tar.gz", r / "user", "a.tar.gz", r / "cfg")
                self.assertFalse((r / "x.txt").exists())

    def test_garbage_and_7z_are_clear_errors(self):
        with tempfile.TemporaryDirectory() as r:
            r = Path(r)
            (r / "a.tar.gz").write_bytes(b"not an archive")
            with self.assertRaises(ValueError):
                install.install_archive(r / "a.tar.gz", r / "user", "a.tar.gz", r / "cfg")
            with self.assertRaisesRegex(ValueError, "re-pack"):
                install.install_archive(r / "a.7z", r / "user", "a.7z", r / "cfg")

    def test_partial_launch_validates_and_reports(self):
        with tempfile.TemporaryDirectory() as r:
            r = Path(r)
            mk(r / "user", "Lib", {"x.txt": ""}, meta={"name": "Lib"})
            mk(r / "user", "A", {"y.txt": ""}, meta={"name": "A", "relationships": [{"rel_type": "dependency", "display_name": "Lib"}]})
            app = GameApp(games.CK3, user_dir=r / "user", workshop_dir=r / "none", game_exe=str(r / "nope"), game_version_="1.7.6",
                          store=Store(r / "p.json"), library=Library(r / "l.json"), autodetect=False)
            pid = app.store.create("p", ["local:Lib", "local:A"])
            for bad in ([], "x", ["local:ghost"]):
                with self.assertRaises(ValueError):
                    app.launch(pid, bad)
            with self.assertRaises(ValueError):  # exe is missing, but the load file was written for just A first
                app.launch(pid, ["local:A"])
            import json
            self.assertEqual(json.loads((r / "user/dlc_load.json").read_text())["enabled_mods"], ["mod/A.mod"])
