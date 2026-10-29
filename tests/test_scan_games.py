"""Scanner/analysis behaviour that differs between games, plus the CK3 and EU5 edge cases carried over."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from modmanager import games, order, scan
from modmanager.descriptor import parse_descriptor, parse_metadata
from tests.helpers import mkmod

L = lambda *n: [f"local:{x}" for x in n]


class Base(unittest.TestCase):
    def setUp(self):
        self.t = tempfile.TemporaryDirectory()
        self.r = Path(self.t.name)
        self.addCleanup(self.t.cleanup)

    def mods(self):
        return scan.scan_mods(self.r)


class UnreadableFolders(Base):
    """Windows answers some folders with an OSError instead of True/False (WinError 448 'untrusted mount point')."""

    def run_with_bad_folder(self, bad):
        real = {n: getattr(Path, n) for n in ("is_dir", "exists")}

        def failing(name):
            def fn(self_):
                if self_.name == bad:
                    raise OSError(448, "The path cannot be traversed because it contains an untrusted mount point", str(self_))
                return real[name](self_)
            return fn
        with mock.patch.object(Path, "is_dir", failing("is_dir")), mock.patch.object(Path, "exists", failing("exists")):
            return self.mods()

    def test_one_unreadable_folder_is_skipped_not_fatal(self):
        mkmod(self.r, "good", "Good Mod")
        mkmod(self.r, "arcane_industrial_age", "Arcane", stub=False)
        mkmod(self.r, "also_good", "Also Good")
        mods = self.run_with_bad_folder("arcane_industrial_age")
        self.assertEqual({m["name"] for m in mods.values()}, {"Good Mod", "Also Good"})

    def test_a_stub_pointing_at_an_unreadable_folder_shows_as_missing(self):
        mkmod(self.r, "arcane_industrial_age", "Arcane")  # with its .mod stub
        mods = self.run_with_bad_folder("arcane_industrial_age")
        self.assertEqual(len(mods), 1)
        self.assertFalse(next(iter(mods.values()))["exists"])

    def test_an_unreadable_workshop_folder_is_skipped(self):
        ws = self.r / "ws"
        for wid in ("111", "222"):
            (ws / wid / ".metadata").mkdir(parents=True)
            (ws / wid / ".metadata/metadata.json").write_text(json.dumps({"name": "W" + wid}))
        real_is_dir = Path.is_dir

        def is_dir(self_):
            if self_.name == "111":
                raise OSError(448, "untrusted mount point")
            return real_is_dir(self_)
        with mock.patch.object(Path, "is_dir", is_dir):
            mods = scan.scan_mods(None, ws)
        self.assertEqual(list(mods), ["ws:222"])


class MetadataLayouts(Base):
    def test_all_three_metadata_locations_and_both_relationship_spellings(self):
        for layout in (".metadata", "metadata", "."):
            for key in ("rel_type", "type"):
                d = mkmod(self.r, f"m_{layout.strip('.') or 'root'}_{key}", deps=["Lib"], incompatible=["Bad"],
                          layout=layout, rel_key=key, meta_id="id1", stub=False)
                m = scan.scan_mods(self.r)[f"local:{d.name}"]
                self.assertEqual((m["dependencies"], m["incompatible"], m["meta_id"]), (["Lib"], ["Bad"], "id1"), (layout, key))

    def test_dependency_ids_are_kept_and_win_over_renamed_display_names(self):
        mkmod(self.r, "Lib", name="Library", meta_id="lib-1")
        mkmod(self.r, "User", deps=[{"id": "lib-1", "display_name": "Old Name Of Library"}])
        mods = self.mods()
        self.assertEqual(mods["local:User"]["dependency_ids"], {"Old Name Of Library": "lib-1"})
        res = order.compute_order(mods, L("User", "Lib"), True)
        self.assertEqual(res["order"], L("Lib", "User"))
        self.assertEqual(res["issues"], [])

    def test_legacy_descriptor_only_mod(self):
        d = self.r / "mod/Legacy"
        d.mkdir(parents=True)
        (d / "descriptor.mod").write_text('name="L # x"\ndependencies={ "Z" }\nsupported_version="1.12.*"\n')
        m = self.mods()["local:Legacy"]
        self.assertEqual((m["name"], m["dependencies"], m["supported_version"]), ("L # x", ["Z"], "1.12.*"))

    def test_folder_without_metadata_is_not_a_mod(self):
        (self.r / "mod/junk").mkdir(parents=True)
        (self.r / "mod/junk/x.txt").write_text("x")
        (self.r / "mod/afile.txt").write_text("x")
        self.assertEqual(self.mods(), {})

    def test_corrupt_metadata_is_reported_not_fatal(self):
        d = mkmod(self.r, "Bad", stub=False)
        (d / ".metadata/metadata.json").write_text("{oops")
        m = self.mods()["local:Bad"]
        self.assertIn("unreadable", m["error"])
        issues = order.validate(self.mods(), ["local:Bad"])
        self.assertTrue(any(i["code"] == "metadata_error" for i in issues))

    def test_wrong_shapes_never_crash(self):
        d = mkmod(self.r, "Odd", stub=False)
        f = d / ".metadata/metadata.json"
        for doc in ('[]', '"x"', 'null', '{"name": null, "tags": null, "relationships": "x"}',
                    '{"relationships": [1, null, {"rel_type": "dependency"}, {"type": 5}]}',
                    '{"game_custom_data": []}', '{"tags": [1, {"a": 1}, "ok"]}'):
            f.write_text(doc)
            m = scan.scan_mods(self.r)["local:Odd"]
            self.assertTrue(m["name"], doc)

    def test_bom_and_unicode_in_metadata(self):
        d = mkmod(self.r, "U", stub=False)
        (d / ".metadata/metadata.json").write_bytes('{"name": "Ünïcødé 帝国"}'.encode("utf-8-sig"))
        self.assertEqual(self.mods()["local:U"]["name"], "Ünïcødé 帝国")

    def test_metadata_is_not_a_conflict(self):
        for n in "AB":
            d = mkmod(self.r, n)
            (d / "thumbnail.png").write_bytes(b"x")
            (d / "descriptor.mod").write_text("x")
        self.assertEqual(scan.find_conflicts(self.mods(), L("A", "B")), [])

    def test_workshop_stub_not_duplicated_and_bare_folder_found(self):
        ws = self.r / "ws/42"
        (ws / ".metadata").mkdir(parents=True)
        (ws / ".metadata/metadata.json").write_text('{"name": "WS"}')
        (self.r / "mod").mkdir()
        (self.r / "mod/ugc_42.mod").write_text('name="WS"\nremote_file_id="42"\npath="/steam/42"\n')
        mkmod(self.r, "Bare", stub=False)
        mods = scan.scan_mods(self.r, self.r / "ws")
        self.assertEqual(sorted(mods), ["local:Bare", "ws:42"])

    def test_ghost_descriptor_pointing_nowhere_is_flagged(self):
        (self.r / "mod").mkdir()
        (self.r / "mod/Ghost.mod").write_text('name="Ghost"\npath="mod/Ghost"\n')
        m = self.mods()["local:Ghost"]
        self.assertFalse(m["exists"])
        self.assertEqual(order.validate(self.mods(), ["local:Ghost"])[0]["code"], "missing_module")


class Parsers(unittest.TestCase):
    def test_descriptor_garbage_never_raises_or_hangs(self):
        for t in ("", "   \n", "= = = {", "name", "name=", "{ } } {", '"unterminated'):
            parse_descriptor(t)

    def test_descriptor_bom_crlf_unquoted_and_escapes(self):
        d = parse_descriptor('name="X"\r\nversion=1.2\r\ntags={\r\n"A"\r\n}\r\n')
        self.assertEqual((d["name"], d["version"], d["tags"]), ("X", "1.2", ["A"]))
        d = parse_descriptor('name="A \\"B\\"" # trailing\nversion="1"\nreplace_path="a"\nreplace_path="b"\n')
        self.assertEqual((d["name"], d["version"], d["replace_path"]), ('A "B"', "1", ["a", "b"]))

    def test_large_descriptor_is_fast(self):
        parse_descriptor('tags={' + ' "t"' * 200000 + ' }')

    def test_metadata_garbage(self):
        for t in ("", "{", "[]", "null", "5", '{"relationships": 3}'):
            parse_metadata(t)

    def test_top_level_keys_quotes_namespaces_prefixes(self):
        t = 'namespace = foo\nfoo.0001 = { x = { } }\n"quoted" = { }\nREPLACE:r = { }\nTRY_INJECT:i = {}\n@v = 3\n'
        self.assertEqual(scan.top_level_keys(t), [("foo.0001", None), ("quoted", None), ("r", "REPLACE"), ("i", "TRY_INJECT")])

    def test_top_level_keys_ignore_comments_strings_and_unbalanced(self):
        t = '# top = { }\n@var = 10\na = { b = { c = 1 } # d = { }\n}\n"q" = { x = "}" }\nafter = { }\n'
        self.assertEqual([k for k, _ in scan.top_level_keys(t)], ["a", "q", "after"])
        scan.top_level_keys("a = { b = { ")
        scan.top_level_keys("} } a = { }")
        self.assertEqual(scan.top_level_keys(""), [])

    def test_localization_keys_by_language(self):
        t = 'l_english:\n a_key:0 "x"\n b.key:12 "y"\n # c:0 "no"\n not a key\nl_german:\n a_key:0 "z"\n'
        self.assertEqual(scan.loc_keys(t), [("l_english", "a_key"), ("l_english", "b.key"), ("l_german", "a_key")])

    def test_def_category(self):
        c = scan.def_category
        self.assertEqual(c("common/traits/a.txt", ("common",)), "common/traits")
        self.assertEqual(c("common/traits/sub/a.txt", ("common",)), "common/traits")
        self.assertEqual(c("common/a.txt", ("common",)), "common")
        self.assertEqual(c("in_game/common/goods/a.txt", ("common",)), "in_game/common/goods")
        self.assertEqual(c("events/e.txt", ("common", "events")), "events")
        self.assertIsNone(c("gfx/x.txt", ("common",)))
        self.assertIsNone(c("a/b/c/common/x/y.txt", ("common",)))  # too deep to be a script folder
        self.assertIsNone(c("events/e.txt", ("common",)))  # EU5 profile: events are not definitions


class Conflicts(Base):
    def test_ck3_style_layout_definition_and_file_conflicts(self):
        mkmod(self.r, "A", files={"common/traits/a.txt": "t1 = { }", "events/e.txt": "x = {}"})
        mkmod(self.r, "B", files={"common/traits/b.txt": "t1 = { }", "events/e.txt": "y = {}"})
        c = {(x["kind"], x["path"]): x for x in scan.find_conflicts(self.mods(), L("B", "A"))}
        self.assertEqual(c[("definition", "common/traits: t1")]["winner"], "local:A")
        self.assertEqual(c[("file", "events/e.txt")]["mods"], L("B", "A"))

    def test_eu5_style_layout_and_def_dirs(self):
        files = {"in_game/common/goods/a.txt": "wood = { }", "in_game/events/e.txt": "ev = {}"}
        mkmod(self.r, "A", files=files)
        mkmod(self.r, "B", files={"in_game/common/goods/b.txt": "wood = { }", "in_game/events/f.txt": "ev = {}"})
        kinds = {x["path"] for x in scan.find_conflicts(self.mods(), L("A", "B"), def_dirs=games.EU5.def_dirs)}
        self.assertEqual(kinds, {"in_game/common/goods: wood"})  # EU5 profile ignores events
        kinds = {x["path"] for x in scan.find_conflicts(self.mods(), L("A", "B"), def_dirs=("common", "events"))}
        self.assertEqual(kinds, {"in_game/common/goods: wood", "in_game/events: ev"})

    def test_same_key_in_different_folders_is_not_a_clash(self):
        mkmod(self.r, "A", files={"common/traits/a.txt": "same = { }"})
        mkmod(self.r, "B", files={"common/decisions/b.txt": "same = { }"})
        self.assertEqual(scan.find_conflicts(self.mods(), L("A", "B")), [])

    def test_same_file_clash_is_only_a_file_conflict(self):
        for n in "AB":
            mkmod(self.r, n, files={"events/e.txt": "x = { }"})
        self.assertEqual([c["kind"] for c in scan.find_conflicts(self.mods(), L("A", "B"))], ["file"])

    def test_three_way_winner_is_last_loaded_and_follows_order(self):
        for n in "ABC":
            mkmod(self.r, n, files={"gfx/x.txt": n, f"common/g/{n}.txt": "k = { }"})
        for order_ in (L("A", "B", "C"), L("C", "B", "A"), L("B", "C", "A")):
            c = {x["kind"]: x for x in scan.find_conflicts(self.mods(), order_)}
            self.assertEqual((c["file"]["mods"], c["file"]["winner"]), (order_, order_[-1]))
            self.assertEqual(c["definition"]["winner"], order_[-1])

    def test_missing_and_unknown_mods_do_not_conflict(self):
        mkmod(self.r, "A", files={"x.txt": "1"})
        mkmod(self.r, "B", files={"x.txt": "2"})
        self.assertEqual(scan.find_conflicts(self.mods(), ["ws:999", *L("A")]), [])
        self.assertEqual(scan.find_conflicts(self.mods(), []), [])

    def test_replace_and_inject_semantics(self):
        mkmod(self.r, "A", files={"common/goods/a.txt": "k = { }"})
        mkmod(self.r, "R", files={"common/goods/r.txt": "REPLACE:k = { }"})
        mkmod(self.r, "I", files={"common/goods/i.txt": "INJECT:k = { }"})
        c = {x["kind"]: x for x in scan.find_conflicts(self.mods(), L("A", "R", "I"))}
        self.assertEqual((c["definition"]["mods"], c["definition"]["severity"]), (L("A", "R"), "info"))  # intentional
        self.assertEqual(c["patch"]["mods"], ["local:I"])  # injectors merge; never owners
        self.assertEqual(c["patch"]["severity"], "info")

    def test_replace_path_wipes_earlier_mods(self):
        mkmod(self.r, "A", files={"common/goods/a.txt": "k = { }", "common/goods/b.txt": "j = { }"})
        mkmod(self.r, "B", files={"common/goods/c.txt": "z = { }"}, extra={"game_custom_data": {"replace_paths": ["common/goods"]}})
        c = [x for x in scan.find_conflicts(self.mods(), L("A", "B")) if x["kind"] == "replace"]
        self.assertEqual((c[0]["mods"], c[0]["path"]), (L("A", "B"), "common/goods/ (2 files)"))
        self.assertEqual([x for x in scan.find_conflicts(self.mods(), L("B", "A")) if x["kind"] == "replace"], [])

    def test_localization_clashes_ignore_replace_folder_and_same_file(self):
        mkmod(self.r, "A", files={"localization/english/a_l_english.yml": 'l_english:\n k:0 "a"\n'})
        mkmod(self.r, "B", files={"localization/english/b_l_english.yml": 'l_english:\n k:0 "b"\n',
                                  "localization/english/replace/z_l_english.yml": 'l_english:\n k:0 "z"\n'})
        c = [x for x in scan.find_conflicts(self.mods(), L("A", "B")) if x["kind"] == "localization"]
        self.assertEqual([(x["path"], x["winner"]) for x in c], [("l_english: k", "local:B")])

    def test_binary_and_odd_encodings_do_not_break_analysis(self):
        for n in "AB":
            mkmod(self.r, n, files={"common/g/x.txt": ""})
            (self.r / "mod" / n / "common/g/x.txt").write_bytes(b"\xff\xfe\x00bad \x80 = { }")
        self.assertTrue(any(x["kind"] == "file" for x in scan.find_conflicts(self.mods(), L("A", "B"))))

    def test_symlinks_are_never_followed(self):
        outside = self.r / "outside"
        outside.mkdir()
        (outside / "secret.txt").write_text("k = { }")
        d = mkmod(self.r, "A", files={"common/g/a.txt": "k = { }"})
        try:
            (d / "common/link").symlink_to(outside, target_is_directory=True)
            (d / "common/g/f.txt").symlink_to(outside / "secret.txt")
        except OSError:
            self.skipTest("symlinks unavailable")
        self.assertNotIn("common/link/secret.txt", scan.list_files(d))
        self.assertNotIn("common/g/f.txt", scan.list_files(d))


class BaseGameComparison(Base):
    def setUp(self):
        super().setUp()
        self.game = self.r / "game"
        (self.game / "common/goods").mkdir(parents=True)
        (self.game / "common/goods/base.txt").write_text("wood = { }\niron = { }")
        (self.game / "events").mkdir()
        (self.game / "events/e.txt").write_text("ev = { }")
        (self.game / "gfx").mkdir()
        (self.game / "gfx/ui.txt").write_text("x")
        (self.game / "readme.txt").write_text("root file")

    def run_(self, order_, only=()):
        return scan.find_conflicts(self.mods(), order_, None, ("common", "events"), (self.game, only))

    def test_override_of_a_base_game_key_is_flagged_vanilla(self):
        mkmod(self.r, "M", files={"common/goods/m.txt": "REPLACE:wood = { }\nnew = { }"})
        c = self.run_(L("M"))
        self.assertEqual([(x["kind"], x["path"], x.get("vanilla")) for x in c], [("definition", "common/goods: wood", True)])
        self.assertEqual(c[0]["mods"], ["__vanilla__", "local:M"])
        self.assertEqual(c[0]["severity"], "info")  # REPLACE is the intended way to override

    def test_plain_redefinition_of_base_key_warns(self):
        mkmod(self.r, "M", files={"common/goods/m.txt": "wood = { }"})
        self.assertEqual(self.run_(L("M"))[0]["severity"], "warn")

    def test_file_override_and_replace_path_against_base(self):
        mkmod(self.r, "M", files={"gfx/ui.txt": "mine", "common/goods/z.txt": "q = { }"},
              extra={"game_custom_data": {"replace_paths": ["common/goods"]}})
        c = {(x["kind"], x["path"]): x for x in self.run_(L("M"))}
        self.assertTrue(c[("file", "gfx/ui.txt")]["vanilla"])
        self.assertTrue(c[("replace", "common/goods/ (1 files)")]["vanilla"])

    def test_two_mods_and_base_is_a_real_conflict_not_vanilla(self):
        mkmod(self.r, "A", files={"common/goods/a.txt": "wood = { }"})
        mkmod(self.r, "B", files={"common/goods/b.txt": "wood = { }"})
        c = self.run_(L("A", "B"))
        self.assertEqual(len(c), 1)
        self.assertNotIn("vanilla", c[0])
        self.assertEqual(c[0]["mods"], ["__vanilla__", "local:A", "local:B"])
        self.assertEqual(c[0]["winner"], "local:B")

    def test_only_limits_which_base_folders_count(self):
        mkmod(self.r, "M", files={"gfx/ui.txt": "mine", "common/goods/m.txt": "wood = { }"})
        self.assertEqual({x["kind"] for x in self.run_(L("M"), only=("common",))}, {"definition"})

    def test_loose_root_files_are_not_base_content_when_limited(self):
        mkmod(self.r, "M", files={"readme.txt": "mine"})
        self.assertEqual(self.run_(L("M"), only=("common",)), [])

    def test_localization_is_never_reported_against_the_base_game(self):
        (self.game / "localization/english").mkdir(parents=True)
        (self.game / "localization/english/b_l_english.yml").write_text('l_english:\n k:0 "base"\n')
        mkmod(self.r, "M", files={"localization/english/m_l_english.yml": 'l_english:\n k:0 "mine"\n'})
        self.assertEqual(self.run_(L("M")), [])

    def test_no_mods_means_no_base_work_and_no_results(self):
        self.assertEqual(self.run_([]), [])

    def test_base_files_are_only_parsed_where_mods_define_keys(self):
        mkmod(self.r, "M", files={"common/goods/m.txt": "new = { }"})
        calls = []
        real = scan._cached
        scan._cached = lambda p, fn: (calls.append(str(p)), real(p, fn))[1]
        try:
            self.run_(L("M"))
        finally:
            scan._cached = real
        self.assertTrue(all("/events/" not in c.replace("\\", "/") for c in calls), calls)  # events/ untouched by any mod


if __name__ == "__main__":
    unittest.main()
