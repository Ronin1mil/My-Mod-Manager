"""The faster scan must give the same answers as the plain way, use threads only where waiting dominates, and say how far it is."""
import random
import tempfile
import threading
import time
import unittest
from pathlib import Path

from modmanager import scan


def reference_top_level_keys(text):
    """The first, plain way of reading definitions: look at every word. The fast one must agree with it."""
    keys, depth = [], 0
    toks = [t for t in scan._TOKEN.findall(text) if t]
    for j, t in enumerate(toks):
        if t == "{":
            depth += 1
        elif t == "}":
            depth = max(0, depth - 1)
        elif depth == 0 and j + 2 < len(toks) and toks[j + 1] == "=" and toks[j + 2] == "{":
            k = t.strip('"')
            m = scan.PATCH_PREFIX.match(k)
            keys.append((m.group(2), m.group(1)) if m else (k, None))
    return keys


class FastKeys(unittest.TestCase):
    def test_same_answers_as_reading_every_word_on_random_text(self):
        rnd = random.Random(7)
        atoms = ["{", "}", "=", "a", "bb", '"q x"', '"', "#c\n", "# {\n", "REPLACE:r", "INJECT:z", "x=", "\n", " ", "==", "{{", "}}",
                 '"unclosed', "k = {", "} }", '"a{b"', '#"', "\t", "k={", "}", "TRY_REPLACE:t", '"quoted key" = {', "# } \n"]
        for _ in range(30000):
            s = "".join(rnd.choice(atoms) for _ in range(rnd.randint(0, 18)))
            self.assertEqual(scan.top_level_keys(s), reference_top_level_keys(s), repr(s))

    def test_same_answers_on_a_realistic_file(self):
        text = ('# traits\nbrave = {\n  # a { in a comment\n  icon = "gfx/{x}.dds"\n  cost = { gold = 100 }\n}\n'
                'REPLACE:wise = { a = { b = { c = 1 } } }\nINJECT:old = { x = 1 }\nloose = value\n"quoted" = { y = 2 }\n} stray\nafter = { }\n')
        self.assertEqual(scan.top_level_keys(text), reference_top_level_keys(text))
        self.assertEqual([k for k, _ in scan.top_level_keys(text)], ["brave", "wise", "old", "quoted", "after"])


class Threads(unittest.TestCase):
    def test_a_fast_call_stays_in_line_and_a_waiting_one_goes_to_threads(self):
        names = set()

        def fast(x):
            names.add(threading.current_thread().name)
            return x * 2

        self.assertEqual(scan._adaptive_map(fast, list(range(60)), 0.003), [x * 2 for x in range(60)])
        self.assertEqual(names, {threading.current_thread().name})
        names.clear()

        def waiting(x):
            names.add(threading.current_thread().name)
            time.sleep(0.006)
            return x * 2

        self.assertEqual(scan._adaptive_map(waiting, list(range(60)), 0.003), [x * 2 for x in range(60)])   # order is kept
        self.assertGreater(len(names), 1, "a slow disk should be read on several threads")

    def test_a_short_list_never_starts_threads_and_keeps_order(self):
        self.assertEqual(scan._adaptive_map(lambda x: x, [3, 1, 2], 0), [3, 1, 2])
        self.assertEqual(list(scan._pmap(lambda x: x + 1, range(100))), list(range(1, 101)))


class Prefetch(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        saved = dict(scan._parse_cache)
        self.addCleanup(lambda: (scan._parse_cache.clear(), scan._parse_cache.update(saved)))
        self.r = Path(self.tmp.name)
        self.files = []
        for i in range(30):
            f = self.r / f"f{i}.txt"
            f.write_text(f"key_{i} = {{ a = 1 }}\n")
            self.files.append((str(f), scan.top_level_keys))

    def test_everything_is_read_once_then_only_checked(self):
        trusted = set()
        scan.prefetch(self.files, trusted)
        self.assertEqual(len(trusted), 30)
        self.assertEqual(scan._parse_cache[(self.files[3][0], "top_level_keys")][2], frozenset({("key_3", None)}))
        reads = []
        real = scan._probe_many
        scan._probe_many = lambda items: (reads.append(len(items)), real(items))[1]
        try:
            scan.prefetch(self.files, trusted)   # already checked since the last disk read: nothing to do
            self.assertEqual(reads, [])
            scan.prefetch(self.files, set())     # not trusted yet: checked by stat, nothing re-parsed
        finally:
            scan._probe_many = real
        self.assertGreater(sum(reads), 0)

    def test_a_changed_file_is_read_again_and_an_unreadable_one_is_skipped(self):
        scan.prefetch(self.files, set())
        Path(self.files[0][0]).write_text("other = { }\n# longer than before\n")
        Path(self.files[1][0]).unlink()
        scan.prefetch(self.files, set())
        self.assertEqual(scan._parse_cache[(self.files[0][0], "top_level_keys")][2], frozenset({("other", None)}))

    def test_progress_is_reported_and_a_stop_request_ends_it(self):
        said = []
        scan.prefetch(self.files, set(), said.append)
        self.assertTrue(said and said[-1] == "reading files 30 of 30", said)
        with self.assertRaises(scan.ScanCancelled):
            scan.prefetch(self.files, set(), None, lambda: True)

    def test_find_conflicts_reports_listing_reading_and_comparing(self):
        mods = {}
        for n in "AB":
            d = self.r / "m" / n / "common/traits"
            d.mkdir(parents=True)
            (d / "t.txt").write_text("shared = { }\n")
            mods[f"local:{n}"] = {"id": f"local:{n}", "exists": True, "root": str(self.r / "m" / n), "replace_path": []}
        said = []
        res = scan.find_conflicts(mods, ["local:A", "local:B"], None, ("common",), progress=said.append)
        self.assertEqual([c["kind"] for c in res], ["file"])
        self.assertTrue(any(m.startswith("listing files") for m in said) and any(m.startswith("reading files") for m in said))
        self.assertEqual(said[-1], "comparing 2 mods")


if __name__ == "__main__":
    unittest.main()
