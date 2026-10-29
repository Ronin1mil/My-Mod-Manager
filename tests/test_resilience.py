"""A folder the operating system refuses to open must never take the app down.

Reproduces the 0.5.0 failure from a real error log: Windows raised OSError WinError 448 ("untrusted mount point")
from Path.is_dir() on one mod folder, and the whole game failed to load. Every mod folder is made unreadable in
turn, in every way a filesystem probe can fail, and the whole app (load, warnings, conflicts, file tree, launch
file) has to keep answering with the other mods intact.
"""
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from modmanager import games
from modmanager.library import Library
from modmanager.server import GameApp
from modmanager.store import Store
from tests.helpers import mkmod, mkworkshop

PROBES = ("is_dir", "is_file", "exists", "iterdir", "stat")


def winerror_448(path):
    return OSError(448, "The path cannot be traversed because it contains an untrusted mount point", str(path))


class Unreadable(unittest.TestCase):
    def setUp(self):
        t = tempfile.TemporaryDirectory()
        self.addCleanup(t.cleanup)
        self.r = Path(t.name)
        p = mock.patch.dict(os.environ, {"MODMANAGER_CONFIG_DIR": str(self.r / "cfg")})
        p.start()
        self.addCleanup(p.stop)
        self.user, self.ws = self.r / "user", self.r / "ws"
        (self.user / "mod").mkdir(parents=True)
        self.ws.mkdir()
        mkmod(self.user, "plain", "Plain Mod", files={"common/goods/a.txt": "g = {}"})
        mkmod(self.user, "stubbed", "Stubbed Mod", files={"common/goods/a.txt": "g = {}"})
        mkmod(self.user, "bare", "Bare Folder Mod", stub=False, files={"common/goods/b.txt": "h = {}"})
        mkworkshop(self.ws, 111, "Workshop One", files={"common/goods/c.txt": "w = {}"})
        mkworkshop(self.ws, 222, "Workshop Two", files={"common/goods/d.txt": "v = {}"})
        self.names = ["plain", "stubbed", "bare", "111", "222"]
        self.exe = self.r / "game.sh"  # a stand-in for the game so Play has something to start
        self.exe.write_text("#!/bin/sh\nexit 0\n")
        self.exe.chmod(0o755)

    def app(self):
        return GameApp(games.VIC3, user_dir=self.user, workshop_dir=self.ws, game_exe=str(self.exe),
                       game_version_="1.0.0", store=Store(self.r / "p.json"), library=Library(self.r / "l.json"),
                       autodetect=False, opener=lambda u: None)

    def broken(self, bad, probes=PROBES):
        """Patch Path so the chosen probes raise for `bad` and anything inside it."""
        real = {n: getattr(Path, n) for n in probes}

        def wrap(name):
            def fn(self_, *a, **k):
                if bad in self_.parts:
                    raise winerror_448(self_)
                return real[name](self_, *a, **k)
            return fn
        stack = [mock.patch.object(Path, n, wrap(n)) for n in probes]
        return _All(stack)

    def test_each_folder_in_turn_every_kind_of_failure(self):
        for bad in self.names:
            for probe in PROBES:
                with self.subTest(folder=bad, probe=probe), self.broken(bad, (probe,)):
                    a = self.app()
                    expected = {"Plain Mod", "Stubbed Mod", "Bare Folder Mod", "Workshop One", "Workshop Two"}
                    expected -= {{"plain": "Plain Mod", "stubbed": "Stubbed Mod", "bare": "Bare Folder Mod",
                                  "111": "Workshop One", "222": "Workshop Two"}[bad]}
                    s = a.state()
                    names = {m["name"] for m in s["mods"]}
                    self.assertTrue(expected <= names, f"lost a healthy mod: {sorted(names)}")

    def test_the_whole_app_keeps_working_with_one_folder_unreadable(self):
        for bad in self.names:
            with self.subTest(folder=bad), self.broken(bad):
                a = self.app()
                s = a.state()
                ids = [m["id"] for m in s["mods"] if m["exists"]]
                self.assertTrue(ids, "nothing left")
                pid = a.store.create("T", ids)
                a.analyse(pid, conflicts=False)
                a.analyse(pid)
                a.conflicts_job(pid)
                a.tree_job(pid)
                res = a.launch(pid)  # writes the load file from the mods that can be read
                data = json.loads((self.user / games.VIC3.load_file).read_text())
                self.assertEqual(res["written"], len(data["enabled_mods"]))

    def test_everything_unreadable_at_once_gives_an_empty_list_not_a_crash(self):
        real = {n: getattr(Path, n) for n in PROBES}

        def wrap(name):
            def fn(self_, *a, **k):
                if str(self.user) in str(self_) or str(self.ws) in str(self_):
                    if self_ in (self.user, self.ws):
                        return real[name](self_, *a, **k)  # the two roots themselves are fine
                    raise winerror_448(self_)
                return real[name](self_, *a, **k)
            return fn
        with _All([mock.patch.object(Path, n, wrap(n)) for n in PROBES]):
            a = self.app()
            s = a.state()
            self.assertEqual([m for m in s["mods"] if m["exists"]], [])


class _All:
    def __init__(self, patches):
        self.patches = patches

    def __enter__(self):
        for p in self.patches:
            p.start()
        return self

    def __exit__(self, *exc):
        for p in reversed(self.patches):
            p.stop()
        return False


if __name__ == "__main__":
    unittest.main()
