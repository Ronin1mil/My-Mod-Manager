"""Switching playsets must be a lookup, not a new scan: conflict answers are kept, a scan nobody waits for any more stops,
coming back to the window costs nothing when no mod changed, and what was parsed survives a restart."""
import os
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest import mock

from modmanager import games, scan
from modmanager.server import GameApp, Hub
from modmanager.store import GlobalSettings
from tests.helpers import mkmod


class _Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.r = Path(self.tmp.name)
        p = mock.patch.dict(os.environ, {"MODMANAGER_CONFIG_DIR": str(self.r / "cfg")})
        p.start()
        self.addCleanup(p.stop)
        self.addCleanup(self.tmp.cleanup)
        self.user = self.r / "user"
        for n in "ABC":
            mkmod(self.user, n, files={"common/traits/t.txt": f"shared = {{ }}\nonly_{n} = {{ }}\n", f"events/{n}.txt": "e = { }"})
        self.app = GameApp(games.VIC3, user_dir=str(self.user), workshop_dir=str(self.r / "ws"), autodetect=False)
        self.ids = sorted(self.app.mods)
        self.p1 = self.app.store.create("one", self.ids)
        self.p2 = self.app.store.create("two", self.ids[:2])


class Switching(_Base):
    def test_a_second_visit_returns_the_same_answer_without_scanning(self):
        first = self.app.conflicts_job(self.p1)()
        with mock.patch("modmanager.scan.find_conflicts", side_effect=AssertionError("scanned again")):
            again = self.app.conflicts_job(self.p1)()
        self.assertIs(first, again)
        self.assertTrue(any(c["kind"] == "definition" for c in first["conflicts"]))

    def test_another_playset_with_another_order_is_its_own_answer(self):
        a = self.app.conflicts_job(self.p1)()
        b = self.app.conflicts_job(self.p2)()
        self.assertIsNot(a, b)
        self.assertEqual(len({m for c in a["conflicts"] if c["kind"] == "definition" for m in c["mods"]}), 3)
        self.assertEqual(len({m for c in b["conflicts"] if c["kind"] == "definition" for m in c["mods"]}), 2)
        self.assertIs(a, self.app.conflicts_job(self.p1)())

    def test_a_full_rescan_forgets_answers_but_a_light_one_with_no_change_keeps_them(self):
        a = self.app.conflicts_job(self.p1)()
        gen = self.app.scan_gen
        self.assertFalse(self.app.rescan(light=True))
        self.assertEqual(self.app.scan_gen, gen)
        self.assertIs(a, self.app.conflicts_job(self.p1)())
        self.app.rescan()   # the Rescan button: files inside mods may have changed
        self.assertGreater(self.app.scan_gen, gen)
        self.assertIsNot(a, self.app.conflicts_job(self.p1)())

    def test_a_light_rescan_that_finds_a_new_mod_starts_over(self):
        a = self.app.conflicts_job(self.p1)()
        gen = self.app.scan_gen
        mkmod(self.user, "D", files={"common/traits/t.txt": "shared = { }"})
        self.assertTrue(self.app.rescan(light=True))
        self.assertGreater(self.app.scan_gen, gen)
        self.assertIsNot(a, self.app.conflicts_job(self.p1)())

    def test_a_file_removed_from_a_mod_is_noticed_after_a_rescan(self):
        clash = lambda res: next(c for c in res["conflicts"] if c["kind"] == "file" and c["path"] == "common/traits/t.txt")
        self.assertIn("local:C", clash(self.app.conflicts_job(self.p1)())["mods"])
        (self.user / "mod/C/common/traits/t.txt").unlink()
        self.assertIn("local:C", clash(self.app.conflicts_job(self.p1)())["mods"])   # not until the mods are read again
        self.app.rescan()
        self.assertNotIn("local:C", clash(self.app.conflicts_job(self.p1)())["mods"])

    def test_a_newer_request_stops_the_older_scan(self):
        real = scan._cached
        seen = threading.Event()
        gate = threading.Event()

        def slow(path, fn, trusted=None):
            seen.set()
            gate.wait(5)
            return real(path, fn, trusted)

        out = {}
        with mock.patch("modmanager.scan._cached", slow):
            old = self.app.conflicts_job(self.p1)
            t = threading.Thread(target=lambda: out.update(old=old()))
            t.start()
            self.assertTrue(seen.wait(5))
            new = self.app.conflicts_job(self.p2)   # the user clicked another playset
            gate.set()
            t.join(10)
            res = new()
        self.assertTrue(out["old"].get("cancelled"))
        self.assertTrue(out["old"]["pending"])
        self.assertFalse(res.get("cancelled"))
        self.assertFalse(res["pending"])

    def test_a_cancelled_scan_is_not_remembered(self):
        with mock.patch("modmanager.scan.find_conflicts", side_effect=scan.ScanCancelled()):
            self.assertTrue(self.app.conflicts_job(self.p1)()["cancelled"])
        self.assertFalse(self.app.conflicts_job(self.p1)().get("cancelled"))

    def test_the_background_scan_gives_way_to_the_user(self):
        bg = self.app.conflicts_job(self.p1, background=True)
        self.app.conflicts_job(self.p2)   # a request from the user arrives before the background scan runs
        self.assertTrue(bg().get("cancelled"))

    def test_the_background_scan_fills_every_playset(self):
        self.app.prewarm_lock = threading.RLock()
        self.app.start_prewarm()
        self.app._prewarm.join(20)
        self.assertFalse(self.app._prewarm.is_alive())
        with mock.patch("modmanager.scan.find_conflicts", side_effect=AssertionError("scanned again")):
            self.app.conflicts_job(self.p1)()
            self.app.conflicts_job(self.p2)()
        self.assertTrue(self.app.parse_cache_file().is_file())

    def test_no_background_work_unless_a_hub_asks_for_it(self):
        self.app.start_prewarm()
        self.assertIsNone(self.app._prewarm)

    def test_a_hub_that_asks_starts_it_for_each_game(self):
        hub = Hub(settings=GlobalSettings(self.r / "g.json"), gamelist=[games.VIC3], prewarm=True,
                  factory=lambda g, **kw: GameApp(g, user_dir=str(self.user), workshop_dir=str(self.r / "ws"), autodetect=False))
        app = hub.app("vic3")
        self.assertIs(app.prewarm_lock, hub.lock)
        app._prewarm.join(20)
        self.assertFalse(app._prewarm.is_alive())


class Boot(_Base):
    """The start-up pass: everything slow is done, and reported, before the window opens."""

    def _hub(self):
        return Hub(settings=GlobalSettings(self.r / "g.json"), gamelist=[games.VIC3],
                   factory=lambda g, **kw: GameApp(g, user_dir=str(self.user), workshop_dir=str(self.r / "ws"), autodetect=False))

    def test_boot_works_out_every_playset_and_says_what_it_does(self):
        from modmanager.server import boot
        hub = self._hub()
        hub.settings.update(last_game="vic3")
        app = hub.app("vic3")
        for ps in list(app.store.data["playsets"]):
            app.store.delete(ps)
        a = app.store.create("one", self.ids)
        b = app.store.create("two", self.ids[:2])
        said = []
        boot(hub, said.append)
        text = "\n".join(said)
        self.assertIn("Victoria 3: 3 mods", text)
        self.assertIn('playset 1 of 2', text)
        self.assertIn('playset 2 of 2 "two"', text)
        self.assertTrue(said[-1].startswith("Ready"))
        with mock.patch("modmanager.scan.find_conflicts", side_effect=AssertionError("scanned again")):
            app.conflicts_job(a)()
            app.conflicts_job(b)()
        self.assertTrue(app.parse_cache_file().is_file(), "what was read is saved for the next start")

    def test_boot_does_nothing_for_a_game_never_used(self):
        from modmanager.server import boot
        hub = Hub(settings=GlobalSettings(self.r / "g.json"), gamelist=[games.CK3])
        said = []
        boot(hub, said.append)   # no last game, no folder for it yet
        self.assertEqual(said, [])
        self.assertNotIn("ck3", hub.apps)

    def test_after_boot_changes_are_worked_out_in_the_background_again(self):
        hub = self._hub()
        app = hub.app("vic3")
        self.assertIsNone(app.prewarm_lock)
        hub.enable_prewarm()
        self.assertIs(app.prewarm_lock, hub.lock)


class ParseCache(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.r = Path(self.tmp.name)
        self.addCleanup(self.tmp.cleanup)
        saved = dict(scan._parse_cache), set(scan._loaded)
        self.addCleanup(lambda: (scan._parse_cache.clear(), scan._parse_cache.update(saved[0]), scan._loaded.clear(), scan._loaded.update(saved[1])))
        scan._parse_cache.clear()
        scan._loaded.clear()
        self.f = self.r / "a.txt"
        self.f.write_text("k = { }\nREPLACE:r = { }\n")

    def test_what_was_parsed_comes_back_after_a_restart(self):
        want = scan._cached(str(self.f), scan.top_level_keys)
        scan.save_cache(self.r / "c.gz")
        scan._parse_cache.clear()
        scan._loaded.clear()
        self.assertEqual(scan.load_cache(self.r / "c.gz"), 1)
        with mock.patch("modmanager.scan._read", side_effect=AssertionError("read the file again")):
            self.assertEqual(scan._cached(str(self.f), scan.top_level_keys), want)
        self.assertIn(("r", "REPLACE"), want)

    def test_a_file_changed_since_it_was_saved_is_read_again(self):
        scan._cached(str(self.f), scan.top_level_keys)
        scan.save_cache(self.r / "c.gz")
        scan._parse_cache.clear()
        scan._loaded.clear()
        scan.load_cache(self.r / "c.gz")
        self.f.write_text("changed = { }\n# longer than before\n")
        self.assertEqual({k for k, _ in scan._cached(str(self.f), scan.top_level_keys)}, {"changed"})

    def test_a_trusted_file_is_not_looked_at_again_until_the_mods_are_read_again(self):
        trusted = set()
        scan._cached(str(self.f), scan.top_level_keys, trusted)
        with mock.patch("os.stat", side_effect=AssertionError("stat-ed again")):
            scan._cached(str(self.f), scan.top_level_keys, trusted)

    def test_a_damaged_or_foreign_cache_file_is_a_cold_start_not_an_error(self):
        for name, data in (("junk.gz", b"not gzip"), ("empty.gz", b"")):
            (self.r / name).write_bytes(data)
            self.assertEqual(scan.load_cache(self.r / name), 0)
        import gzip
        with gzip.open(self.r / "old.gz", "wt") as f:
            f.write('{"format": 99, "entries": []}')
        self.assertEqual(scan.load_cache(self.r / "old.gz"), 0)
        with gzip.open(self.r / "bad.gz", "wt") as f:
            f.write('{"format": 1, "entries": [["p", "top_level_keys"]]}')
        self.assertEqual(scan.load_cache(self.r / "bad.gz"), 0)


if __name__ == "__main__":
    unittest.main()
