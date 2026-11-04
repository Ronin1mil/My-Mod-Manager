import hashlib
import json
import os
import struct
import sys
import time
import unittest
from pathlib import Path
from unittest import mock

from modmanager import games, rnw
from modmanager.rnw_fields import CHANGE_FIELDS
from tests.helpers import GameCase, mkmod, mkworkshop

STUB = Path(__file__).with_name("rnwstub.py")
ALPHA = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"
HEAD = struct.Struct(">BBQBBBB")


def leb(v):
    out = bytearray()
    while True:
        b, v = v & 0x7F, v >> 7
        out.append(b | (0x80 if v else 0))
        if not v:
            return bytes(out)


def make_code(preset=1, seed=42, ver=(1, 1, 0), changes=None, fmt=2):
    """A world code written the way RNW's docs describe the format (so the decoder is checked against the format)."""
    flags = 1 if changes else 0
    body = HEAD.pack(fmt, preset, seed, *ver, flags)
    if changes and fmt == 2:
        items = sorted((CHANGE_FIELDS.index(k), v) for k, v in changes.items())
        body += bytes([len(items)]) + b"".join(bytes([n]) + leb(v) for n, v in items)
    elif changes:
        import zlib
        packed = zlib.compress(json.dumps(changes).encode())
        body += struct.pack(">H", len(packed)) + packed
    body += hashlib.sha256(body).digest()[:3]
    bits = len(body) * 8
    digits = -(-bits // 5)
    num = int.from_bytes(body, "big") << (digits * 5 - bits)
    text = "".join(ALPHA[(num >> (5 * i)) & 31] for i in range(digits - 1, -1, -1))
    return "-".join(["RNW1"] + [text[i:i + 5] for i in range(0, len(text), 5)])


CODE = make_code(1, 42, changes={"new_world.land_permille": 350, "natives.state_locations": 7, "rolls.peoples": 2})


def make_rnworld(path, code=None, **over):
    """A .rnworld file like the one Random New World exports for one map: a zip with rnworld.json, world.json, atlas.json, a picture."""
    import hashlib
    import zipfile
    world = {"code": code or CODE, "created": 1793819884, "game_build": "26377361", "generator": "1.1.0", "id": "nfnoplzpxt", "name": "My island", "notes": "n",
             "preset": "continents", "seed": 42, "seconds": 218.1, "user_tag": "ISL", "schema": 1, "record": {"settings": {"new_world": {"land_permille": 350}}}}
    world.update(over.pop("world", {}))
    body = json.dumps(world).encode()
    head = {"format": 1, "kind": "world", "exported_by": "1.1.0", "files": {"world.json": hashlib.sha256(body).hexdigest()}}
    head.update(over.pop("head", {}))
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("rnworld.json", json.dumps(head))
        z.writestr("world.json", over.pop("body", body))
        z.writestr("atlas.json", "{}")
        z.writestr("atlas_labels.png", b"\x89PNG")
    return Path(path)


class Codes(unittest.TestCase):
    def test_decodes_preset_seed_generator_and_changes(self):
        d = rnw.decode_code(CODE)
        self.assertEqual((d["preset"], d["seed"], d["generator"]), ("continents", 42, "1.1.0"))
        self.assertEqual(d["changes"], {"new_world": {"land_permille": 350}, "natives": {"state_locations": 7}, "rolls": {"peoples": 2}})

    def test_a_plain_code_has_no_changes_and_a_64_bit_seed_is_kept_exact(self):
        d = rnw.decode_code(make_code(6, 2 ** 64 - 1))
        self.assertEqual((d["preset"], d["seed"], d["changes"]), ("wall", 2 ** 64 - 1, None))

    def test_json_changes_format_is_read(self):
        d = rnw.decode_code(make_code(3, 5, changes={"new_world": {"landform": 2}}, fmt=1))
        self.assertEqual(d["changes"], {"new_world": {"landform": 2}})

    def test_case_spaces_dashes_and_look_alike_letters_are_forgiven(self):
        messy = " " + CODE.lower().replace("-", " ").replace("0", "o").replace("1", "l", 1) + " "
        self.assertEqual(rnw.decode_code(messy)["seed"], 42)
        self.assertEqual(rnw.norm_code(messy), CODE)

    def test_typo_junk_and_other_text_are_refused_with_a_reason(self):
        typo = CODE[:-1] + ("A" if CODE[-1] != "A" else "B")
        for bad, word in ((typo, "typo"), ("hello", "RNW1"), ("RNW1-", "characters"), ("RNW1-AAAAA", "short"), ("RNW1-U!U", "characters")):
            with self.assertRaises(rnw.CodeError) as cm:
                rnw.decode_code(bad)
            self.assertIn(word, str(cm.exception))

    def test_a_compression_bomb_in_the_changes_is_not_expanded(self):
        import zlib
        packed = zlib.compress(b"[" + b"0," * 5_000_000 + b"0]")
        body = HEAD.pack(1, 1, 1, 1, 1, 0, 1) + struct.pack(">H", len(packed)) + packed
        body += hashlib.sha256(body).digest()[:3]
        bits = len(body) * 8
        digits = -(-bits // 5)
        num = int.from_bytes(body, "big") << (digits * 5 - bits)
        code = "RNW1-" + "".join(ALPHA[(num >> (5 * i)) & 31] for i in range(digits - 1, -1, -1))
        with self.assertRaises(rnw.CodeError):
            rnw.decode_code(code)

    def test_changes_are_described_in_words(self):
        rows = {r["field"]: r for r in rnw.describe_changes({"new_world": {"land_permille": 350, "expand_oceans": 0, "feature_px": 40}, "resources": {"coal": 2}})}
        self.assertEqual(rows["new_world.land_permille"]["value"], "35 %")
        self.assertEqual(rows["new_world.land_permille"]["label"], "World: land")
        self.assertEqual(rows["new_world.feature_px"]["value"], "40 px")
        self.assertEqual(rows["resources.coal"]["label"], "Resource: coal")

    def test_fields_table_is_the_documented_length(self):
        self.assertEqual(len(CHANGE_FIELDS), 74)   # checked against RNW's worldcode.py; numbers are never reused
        self.assertEqual((CHANGE_FIELDS[0], CHANGE_FIELDS[30], CHANGE_FIELDS[-1]), ("new_world.land_permille", "new_world.expand_oceans", "natives.turbulence_permille"))


class Reading(unittest.TestCase):
    def setUp(self):
        import tempfile
        self.td = tempfile.TemporaryDirectory()
        self.addCleanup(self.td.cleanup)
        self.mods = Path(self.td.name)

    def world(self, folder="rnw_exp_world_abcde23456", receipt=True, desc=True, name="RNW: Continents ABCD"):
        d = self.mods / folder
        (d / ".metadata/rnw-library").mkdir(parents=True)
        (d / ".metadata/metadata.json").write_text(json.dumps({"name": name, "version": "1.1.0", "short_description": f"World {CODE}" if desc else "World"}))
        if receipt:
            (d / ".metadata/rnw-library/world.json").write_text(json.dumps({
                "schema": 1, "id": "abcde23456", "code": CODE, "preset": "continents", "seed": 42, "generator": "1.1.0", "game_build": "26300913",
                "created": 1700000000, "seconds": 88.0, "name": "My world", "record": {"seed": 42, "release": "1.1.0",
                "settings": {"new_world": {"land_permille": 350, "ocean": True}, "inputs": {"a": "b" * 500}}, "output": {"digest": "abc"}}}))
        return d

    def test_world_files_give_the_settings(self):
        e = rnw.read_world_folder(self.world())
        self.assertEqual((e["name"], e["id"], e["game_build"], e["preset_title"], e["seed"]), ("My world", "abcde23456", "26300913", "Continents", "42"))
        self.assertEqual(e["specs_from"], ["the world's own files", "the world's code"])
        keys = {r["key"]: r["value"] for r in e["details"]}
        self.assertEqual(keys["settings.new_world.land_permille"], "350")
        self.assertEqual(keys["settings.new_world.ocean"], "yes")
        self.assertFalse(any("inputs" in k or "digest" in k for k in keys))   # manifests and hashes are left out
        self.assertIn("World: land", [c["label"] for c in e["changes"]])

    def test_an_older_world_without_files_is_read_from_the_code_in_its_description(self):
        e = rnw.read_world_folder(self.world(receipt=False))
        self.assertEqual((e["seed"], e["preset"], e["specs_from"]), ("42", "continents", ["the world's code"]))
        self.assertEqual(e["name"], "RNW: Continents ABCD")

    def test_a_world_with_nothing_readable_is_still_listed_with_a_problem_free_blank(self):
        e = rnw.read_world_folder(self.world(receipt=False, desc=False))
        self.assertEqual((e["code"], e["seed"], e["installed"]), ("", "", True))

    def test_a_damaged_code_is_a_problem_text_not_an_error(self):
        d = self.world(receipt=False)
        (d / ".metadata/metadata.json").write_text(json.dumps({"name": "x", "short_description": "RNW1-AAAAA-BBBBB"}))
        e = rnw.read_world_folder(d)
        self.assertTrue(e["problem"])

    def test_other_mods_are_not_worlds(self):
        d = self.mods / "Other"
        (d / ".metadata").mkdir(parents=True)
        (d / ".metadata/metadata.json").write_text("{}")
        self.assertIsNone(rnw.read_world_folder(d))

    def test_broken_or_huge_json_does_not_crash(self):
        d = self.world()
        (d / ".metadata/rnw-library/world.json").write_text("{not json")
        self.assertEqual(rnw.read_world_folder(d)["seed"], "42")   # still read from the code
        (d / ".metadata/rnw-library/world.json").write_text(" " * (rnw.MAX_JSON + 1))
        self.assertTrue(rnw.read_world_folder(d))

    def test_merge_joins_files_library_and_this_apps_record_by_code(self):
        inst = [rnw.read_world_folder(self.world())]
        other = make_code(2, 77)
        lib = [{"id": "abcde23456", "code": CODE, "place": "in_game", "tag": "ABCD", "name": "RNW: Continents ABCD", "starred": True, "notes": "coop"},
               {"id": "kept000000", "code": other, "place": "kept", "preset": "archipelago", "seed": 77, "tag": "KEPT", "name": "Island fun"}]
        rec = {CODE: {"state": "done", "how": "made by this app", "game_version": "1.4.6"},
               make_code(5, 9): {"state": "done", "how": "made by this app"},
               make_code(4, 3): {"state": "failed"}}
        out = rnw.merge_worlds(inst, lib, rec, {"rnw_exp_world_abcde23456": "local:rnw_exp_world_abcde23456"})
        self.assertEqual([w["place"] for w in out], ["in_game", "kept", "code_only"])   # installed first
        first = out[0]
        self.assertTrue(first["starred"] and first["made_here"])
        self.assertEqual((first["notes"], first["mod_id"]), ("coop", "local:rnw_exp_world_abcde23456"))
        self.assertIn("the generator's library", first["specs_from"])
        self.assertIn("this app's record", first["specs_from"])
        self.assertEqual(out[1]["preset_title"], "Archipelago")
        self.assertEqual(len(out), 3)   # the failed record makes no world

    def test_records_survive_a_round_trip_and_keep_only_the_newest(self):
        r = rnw.Records(self.mods / "rec.json")
        for i in range(rnw.MAX_RECORDS + 5):
            r.put(f"c{i}", {"requested_at": i})
        got = r.load()
        self.assertEqual(len(got), rnw.MAX_RECORDS)
        self.assertNotIn("c0", got)
        self.assertIn(f"c{rnw.MAX_RECORDS + 4}", got)


@unittest.skipIf(os.name == "nt", "uses a POSIX shell to hold the output pipe open")
class Rnworld(unittest.TestCase):
    """The .rnworld file: what Random New World exports for one map."""
    def setUp(self):
        import tempfile
        self.td = tempfile.TemporaryDirectory()
        self.addCleanup(self.td.cleanup)
        self.f = Path(self.td.name) / "world.rnworld"

    def test_reads_the_world_record(self):
        w = rnw.read_rnworld(make_rnworld(self.f))
        self.assertEqual((w["code"], w["name"], w["user_tag"]), (CODE, "My island", "ISL"))

    def test_a_real_world_code_from_the_generator_decodes_to_what_its_own_record_says(self):
        # taken from a file exported by Random New World 1.1.0: the code and the record in the same file must agree
        code = "RNW1-082FS-VXRMG-SRB1P-2040G-00870-2Z042-1M1Z8-0Y448-1R8GJ-4XR0C-DA01J-HJAC0"
        d = rnw.decode_code(code)
        self.assertEqual((d["preset"], d["seed"], d["generator"]), ("small_continents", 18225989232370222786, "1.1.0"))
        self.assertEqual(d["changes"]["new_world"], {"land_permille": 318, "location_px": 52, "precious_permille": 2000})
        self.assertEqual(d["changes"]["natives"], {"population_permille": 1800, "hearths_per_10k": 9, "state_share_permille": 440, "empire_permille": 800})

    def test_damaged_odd_and_wrong_files_are_refused_with_a_reason(self):
        import zipfile
        cases = {
            "not a zip": lambda: self.f.write_bytes(b"hello"),
            "wrong kind": lambda: make_rnworld(self.f, head={"kind": "library"}),
            "newer format": lambda: make_rnworld(self.f, head={"format": 2}),
            "checksum": lambda: make_rnworld(self.f, head={"files": {"world.json": "0" * 64}}),
            "no code": lambda: make_rnworld(self.f, world={"code": ""}),
            "bad json": lambda: make_rnworld(self.f, body=b"{nope", head={"files": {}}),
        }
        for name, build in cases.items():
            build()
            with self.assertRaises(ValueError, msg=name):
                rnw.read_rnworld(self.f)
        with zipfile.ZipFile(self.f, "w") as z:   # a zip without the two description files
            z.writestr("x.txt", "x")
        with self.assertRaises(ValueError):
            rnw.read_rnworld(self.f)

    def test_a_huge_description_is_not_opened(self):
        make_rnworld(self.f, body=b" " * (rnw.RNWORLD_LIMITS["world.json"] + 10), head={"files": {}})
        with self.assertRaises(ValueError):
            rnw.read_rnworld(self.f)


class Pick(unittest.TestCase):
    """The system's folder window (pickfolder.py), with a fake program instead of a window."""

    def run_with(self, out, code=0, start=""):
        import tempfile
        from types import SimpleNamespace
        from modmanager import pickfolder
        seen = {}

        def fake(argv, **kw):
            seen.update(argv=argv, env=kw["env"])
            return SimpleNamespace(stdout=out, returncode=code)
        with mock.patch.object(pickfolder, "_powershell", return_value=None):
            return pickfolder.pick_folder("Choose", start, runner=fake), seen

    def test_a_chosen_folder_is_returned(self):
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            res, seen = self.run_with(d + "\n", start=d)
            self.assertEqual(res, {"path": d, "cancelled": False, "error": ""})
            self.assertEqual(seen["env"]["RMM_PICK_START"], d)       # the title and start folder travel in the environment,
            self.assertNotIn(d, " ".join(seen["argv"]))             # never inside the script text

    def test_windows_gets_the_explorer_style_window_with_the_old_one_only_as_a_fallback(self):
        import base64
        from types import SimpleNamespace
        from modmanager import pickfolder
        seen = {}

        def fake(argv, **kw):
            seen["argv"] = argv
            return SimpleNamespace(stdout="", returncode=0)
        with mock.patch.object(pickfolder, "_powershell", return_value="powershell.exe"):
            pickfolder.pick_folder("Choose", "", runner=fake)
        self.assertIn("-EncodedCommand", seen["argv"])
        script = base64.b64decode(seen["argv"][seen["argv"].index("-EncodedCommand") + 1]).decode("utf-16-le")
        self.assertIn("IRmmFileDialog", pickfolder.CSHARP)
        self.assertIn("0x20", pickfolder.CSHARP)                                  # FOS_PICKFOLDERS: Explorer's window in "choose a folder" mode
        self.assertLess(script.index("RmmFolder]::Pick"), script.index("FolderBrowserDialog"))   # the old tree window comes second

    def test_cancel_and_a_missing_window_are_told_apart(self):
        self.assertTrue(self.run_with("")[0]["cancelled"])           # Cancel: nothing printed, exit 0
        res = self.run_with("", code=1)[0]                           # no window program on this PC
        self.assertEqual((res["cancelled"], bool(res["error"])), (False, True))
        self.assertTrue(self.run_with("/not/a/folder/anywhere")[0]["cancelled"])   # a path that is not a folder is not accepted


class Hang(unittest.TestCase):
    def test_a_command_whose_child_keeps_the_pipe_open_still_ends_on_time(self):
        # on Windows rnw.cmd starts a child program; killing only cmd.exe left the pipe open and the page loaded for ever
        import subprocess
        gen = rnw.Generator(Path("."), None, None, ["sh", "-c", "sleep 30 & sleep 30"], "test")
        start = time.time()
        with mock.patch.object(rnw, "KILL_GRACE", 1), mock.patch.object(rnw, "_kill_tree", lambda p: p.kill()):
            with self.assertRaises(subprocess.TimeoutExpired):
                rnw.run_cli(gen, ["worlds"], timeout=1)
        self.assertLess(time.time() - start, 8)

    def test_the_program_gets_no_keyboard_input(self):
        gen = rnw.Generator(Path("."), None, None, ["sh", "-c", "read x; echo got:$x"], "test")
        self.assertEqual(rnw.run_cli(gen, ["worlds"], timeout=10)[:2], (0, "got:\n"))


class Finding(unittest.TestCase):
    def setUp(self):
        import tempfile
        self.td = tempfile.TemporaryDirectory()
        self.addCleanup(self.td.cleanup)
        self.r = Path(self.td.name)

    def test_finds_the_command_line_and_the_window_program_not_the_uninstaller(self):
        d = self.r / "ws/3829217331/bin"
        d.mkdir(parents=True)
        for n in ("rnw.cmd", "RandomNewWorld.exe", "unins000.exe", "crashpad_handler.exe"):
            (d / n).write_text("x")
        g = rnw.find_generator("", [(self.r / "ws/3829217331", "the Steam Workshop")])
        self.assertEqual((g.cmd.name, g.launcher.name, g.how), ("rnw.cmd", "RandomNewWorld.exe", "the Steam Workshop"))
        self.assertTrue(g.public()["can_open"])

    def test_the_chosen_folder_wins_and_a_file_means_its_folder(self):
        a, b = self.r / "a", self.r / "b"
        for d in (a, b):
            d.mkdir()
            (d / "rnw.cmd").write_text("x")
        g = rnw.find_generator(str(b / "rnw.cmd"), [(a, "the Steam Workshop")])
        self.assertEqual(g.folder, b)

    def test_nothing_found_is_none(self):
        (self.r / "empty").mkdir()
        self.assertIsNone(rnw.find_generator("", [(self.r / "empty", "x"), (self.r / "missing", "y")]))

    def test_on_windows_the_window_program_alone_cannot_run_commands(self):
        # a real Workshop copy held only "Random New World Generator.exe"; --cli on it sat open for 214 s and printed nothing
        d = self.r / "g2"
        d.mkdir()
        (d / "Random New World Generator.exe").write_text("x")
        g = rnw.find_generator(str(d))
        self.assertEqual(g.launcher.name, "Random New World Generator.exe")
        with mock.patch.object(rnw.os, "name", "nt"):
            self.assertFalse(g.can_run)
            with self.assertRaises(ValueError):
                g.argv(["worlds"])
        (d / "rnw.cmd").write_text("x")
        g2 = rnw.find_generator(str(d))
        with mock.patch.object(rnw.os, "name", "nt"):
            self.assertEqual((g2.can_run, g2.argv(["worlds"])), (True, [str(d / "rnw.cmd"), "worlds"]))

    def test_arguments_that_could_reach_the_shell_are_refused(self):
        for bad in ("&calc", "a b", "%PATH%", "x|y", "..\\x", "", "-x", 'a"b', "a\nb", "--Preset", "--" + "a" * 40, 5):
            with self.assertRaises(ValueError, msg=repr(bad)):
                rnw.check_args([bad])
        self.assertEqual(rnw.check_args(["world", CODE, "--install", "abcde23456", "rnw_exp_world_abc"]),
                         ["world", CODE, "--install", "abcde23456", "rnw_exp_world_abc"])

    def test_json_after_progress_lines_is_found(self):
        self.assertEqual(rnw.parse_json('[ 5%] start x\n{\n "code": "a"\n}\n'), {"code": "a"})
        self.assertEqual(rnw.parse_json("[1, 2]"), [1, 2])
        self.assertIsNone(rnw.parse_json("nope"))
        self.assertIsNone(rnw.parse_json(""))


class Route(GameCase):
    GAME = games.EU5

    def setUp(self):
        super().setUp()
        self.mods_dir = self.user() / "mod"
        self.worlds_file = self.r / "worlds.json"
        self.worlds_file.write_text("[]")
        env = {"RNW_STUB_MODS": str(self.mods_dir), "RNW_STUB_WORLDS": str(self.worlds_file), "RNW_STUB_CODE": CODE, "RNW_STUB": "ok"}
        p = mock.patch.dict(os.environ, env)
        p.start()
        self.addCleanup(p.stop)
        self.app = self.hub.app("eu5")
        self.mgr = self.app.rnw_manager()
        self.mgr._generator = rnw.Generator(self.r, prefix=[sys.executable, str(STUB)], how="a test stub")

    def wait(self, want=("done", "failed", "cancelled"), seconds=20):
        end = time.time() + seconds
        while time.time() < end:
            job = self.req("GET", "/api/rnw/job")[1]["job"]
            if job and job["state"] in want:
                return job
            time.sleep(0.05)
        self.fail("the job did not finish")

    def test_the_files_listing_starts_no_program_and_reads_the_mod_folder(self):
        d = self.mods_dir / "rnw_exp_world_aaaaa22222"
        (d / ".metadata/rnw-library").mkdir(parents=True)
        (d / ".metadata/metadata.json").write_text(json.dumps({"name": "RNW: Mine", "version": "1"}))
        (d / ".metadata/rnw-library/world.json").write_text(json.dumps({"schema": 1, "id": "aaaaa22222", "code": CODE, "preset": "continents", "seed": 42}))
        self.mgr.runner = lambda *a, **k: self.fail("a program was started")
        res = self.req("GET", "/api/rnw/files")[1]
        self.assertFalse(res["cli_used"])
        self.assertEqual([w["folder"] for w in res["worlds"]], ["rnw_exp_world_aaaaa22222"])
        self.assertEqual(res["notes"], [])

    def make_source(self, name="rnw_exp_world_zzzzz99999", files=3):
        src = self.r / "elsewhere" / name
        (src / ".metadata/rnw-library").mkdir(parents=True)
        (src / ".metadata/metadata.json").write_text(json.dumps({"name": "RNW: Imported", "version": "1"}))
        (src / ".metadata/rnw-library/world.json").write_text(json.dumps({"schema": 1, "id": name[-10:], "code": CODE, "preset": "continents", "seed": 42}))
        for i in range(files):
            (src / "in_game").mkdir(exist_ok=True)
            (src / "in_game" / f"f{i}.txt").write_text("x" * 100)
        return src

    def test_importing_a_world_folder_copies_it_into_the_mod_folder(self):
        src = self.make_source()
        st, res, _ = self.post("/api/rnw/import", {"path": f'"{src}"'})   # Windows "Copy as path" adds quotes
        self.assertEqual(st, 200, res)
        job = self.wait()
        self.assertEqual(job["state"], "done", job)
        self.assertTrue((self.mods_dir / "rnw_exp_world_zzzzz99999/in_game/f2.txt").is_file())
        self.assertFalse(list(self.mods_dir.glob("*.importing")))
        self.assertTrue(src.is_dir())   # the original stays
        names = [w["folder"] for w in self.req("GET", "/api/rnw/files")[1]["worlds"]]
        self.assertIn("rnw_exp_world_zzzzz99999", names)
        st, res, _ = self.post("/api/rnw/import", {"path": str(src)})   # the same world again is refused, not overwritten
        self.assertEqual(st, 400)
        self.assertIn("already", res["error"])

    def test_importing_a_folder_that_holds_several_worlds(self):
        a, b = self.make_source("rnw_exp_world_aaaaa11111"), self.make_source("rnw_exp_world_bbbbb22222")
        self.assertEqual(self.post("/api/rnw/import", {"path": str(a.parent)})[0], 200)
        self.assertEqual(self.wait()["result"]["imported"], ["rnw_exp_world_aaaaa11111", "rnw_exp_world_bbbbb22222"])

    def test_importing_something_that_is_not_a_world_or_is_odd_is_refused(self):
        plain = self.r / "plain"
        plain.mkdir()
        for path in ("", str(self.r / "missing"), str(plain), str(self.mods_dir), "bad\x00path"):
            st, res, _ = self.post("/api/rnw/import", {"path": path})
            self.assertEqual(st, 400, path)
        self.assertEqual(list(self.mods_dir.glob("*.importing")), [])

    def test_importing_a_code_remembers_it_and_lists_the_world_without_building(self):
        st, res, _ = self.post("/api/rnw/import", {"code": CODE.lower()})
        self.assertEqual((st, res["preset"], res["seed"]), (200, "continents", "42"))
        w = self.req("GET", "/api/rnw/files")[1]["worlds"][0]
        self.assertEqual((w["code"], w["installed"], w["place"]), (CODE, False, "code_only"))
        self.assertEqual(self.post("/api/rnw/import", {"code": "RNW1-nonsense"})[0], 400)

    def test_importing_a_rnworld_file_remembers_the_map_with_its_settings(self):
        f = make_rnworld(self.r / "island.rnworld")
        st, res, _ = self.post("/api/rnw/import", {"path": f'"{f}"'})
        self.assertEqual((st, res["worlds"][0]["preset"], res["worlds"][0]["seed"]), (200, "continents", "42"), res)
        w = self.req("GET", "/api/rnw/files")[1]["worlds"][0]
        self.assertEqual((w["name"], w["tag"], w["code"], w["installed"], w["game_build"]), ("My island", "ISL", CODE, False, "26377361"))
        self.assertTrue(any("land_permille" in str(d) for d in w["details"]))          # the generator's own record is shown
        self.assertEqual(self.post("/api/rnw/import", {"path": str(self.r / "nope.rnworld")})[0], 400)

    def test_a_folder_of_rnworld_files_and_a_dropped_file(self):
        folder = self.r / "exports"
        folder.mkdir()
        make_rnworld(folder / "a.rnworld")
        make_rnworld(folder / "b.rnworld", code=make_code(2, 7))
        st, res, _ = self.post("/api/rnw/import", {"path": str(folder)})
        self.assertEqual((st, len(res["worlds"])), (200, 2), res)
        self.assertEqual(len(self.req("GET", "/api/rnw/files")[1]["worlds"]), 2)
        # dropped on the window: the page posts the file to the install route, which hands it to Random New World, not to the mod installer
        raw = (self.r / "drop.rnworld")
        make_rnworld(raw, code=make_code(3, 9))
        st, res, _ = self.req("POST", "/api/install", raw=raw.read_bytes(), headers={"X-Filename": "drop.rnworld"})
        self.assertEqual((st, res.get("rnworld")), (200, True), res)
        self.assertEqual(len(self.req("GET", "/api/rnw/files")[1]["worlds"]), 3)

    def test_the_file_window_asks_for_a_file(self):
        seen = {}
        self.mgr.picker = lambda title, start, **kw: seen.update(title=title, kw=kw) or {"path": "x", "cancelled": False, "error": ""}
        self.post("/api/rnw/pick", {"what": "file"})
        self.assertEqual(seen["kw"], {"kind": "file"})
        self.assertIn(".rnworld", seen["title"])

    def test_other_games_have_no_such_page(self):
        for method, path in (("GET", "/api/rnw/list"), ("POST", "/api/rnw/open")):
            st, res, _ = self.req(method, path, {} if method == "POST" else None, game=games.CK3)
            self.assertEqual(st, 400, path)
            self.assertIn("Europa Universalis V", res["error"])

    def test_list_without_the_generator_says_where_to_get_it(self):
        self.mgr._generator = None
        with mock.patch("modmanager.rnw.find_generator", return_value=None):
            st, res, _ = self.req("GET", "/api/rnw/list")
        self.assertEqual((st, res["generator"], res["worlds"]), (200, None, []))
        self.assertIn("3829217331", res["notes"][0])

    def test_installed_worlds_are_listed_without_the_generator_with_their_specs(self):
        self.mgr._generator = None
        d = mkmod(self.user(), "rnw_exp_world_aaaaa22222", "RNW: Continents AAAA", stub=False,
                  extra={"short_description": f"World {CODE}"})
        with mock.patch("modmanager.rnw.find_generator", return_value=None):
            self.post("/api/rescan", {})
            res = self.req("GET", "/api/rnw/list")[1]
        w = res["worlds"][0]
        self.assertEqual((w["folder"], w["seed"], w["preset_title"], w["mod_id"]), ("rnw_exp_world_aaaaa22222", "42", "Continents", "local:rnw_exp_world_aaaaa22222"))
        self.assertEqual(w["seed"], "42")
        self.assertTrue(d.is_dir())

    def test_list_adds_the_generators_library_and_reports_its_failure_in_words(self):
        self.worlds_file.write_text(json.dumps([{"id": "kept000000", "code": make_code(2, 77), "place": "kept", "preset": "archipelago", "seed": 77,
                                                  "tag": "KEPT", "name": "Island fun", "starred": False}]))
        res = self.req("GET", "/api/rnw/list")[1]
        self.assertTrue(res["cli"]["ok"])
        self.assertEqual([(w["place"], w["installed"]) for w in res["worlds"]], [("kept", False)])
        self.assertEqual(res["generator"]["how"], "a test stub")
        self.worlds_file.write_text("not json")
        res = self.req("GET", "/api/rnw/list")[1]
        self.assertFalse(res["cli"]["ok"])
        self.assertIn("could not be read", res["notes"][0])

    def test_making_a_world_records_its_specs_and_installs_it_into_the_playset_view(self):
        st, res, _ = self.post("/api/rnw/new", {"preset": "continents", "seed": "42"})
        self.assertEqual(st, 200, res)
        self.assertEqual(res["code"], CODE)
        job = self.wait()
        self.assertEqual((job["state"], job["percent"]), ("done", 100), job)
        self.assertEqual(job["result"]["summary"]["locations"], 123)
        self.assertTrue((self.mods_dir / "rnw_exp_world_abcde23456").is_dir())
        w = self.req("GET", "/api/rnw/list")[1]["worlds"][0]
        self.assertTrue(w["made_here"] and w["installed"])
        self.assertEqual((w["seed"], w["preset_title"], w["mod_id"]), ("42", "Continents", "local:rnw_exp_world_abcde23456"))
        rec = json.loads((self.app.cfg / "rnw-worlds.json").read_text())["worlds"][CODE]
        self.assertEqual((rec["state"], rec["preset"], rec["seed"]), ("done", "continents", "42"))
        self.assertEqual(rec["summary"], {"locations": 123, "land": "35 %"})
        self.assertEqual(rec["changes"]["new_world"]["land_permille"], 350)

    def test_a_failed_build_shows_the_generators_own_message_and_is_recorded(self):
        with mock.patch.dict(os.environ, {"RNW_STUB": "fail"}):
            self.post("/api/rnw/new", {"code": CODE})
            job = self.wait()
        self.assertEqual(job["state"], "failed")
        self.assertIn("not enough free memory", job["error"])
        self.assertEqual(json.loads((self.app.cfg / "rnw-worlds.json").read_text())["worlds"][CODE]["state"], "failed")
        self.assertEqual(self.req("GET", "/api/rnw/list")[1]["worlds"], [])

    def test_only_one_job_at_a_time_and_cancel_stops_it(self):
        with mock.patch.dict(os.environ, {"RNW_STUB": "hang"}):
            self.post("/api/rnw/new", {"code": CODE})
            st, res, _ = self.post("/api/rnw/new", {"code": CODE})
            self.assertEqual(st, 400)
            self.assertIn("already working", res["error"])
            self.assertEqual(self.post("/api/rnw/cancel")[0], 200)
            job = self.wait(seconds=15)
        self.assertEqual(job["state"], "cancelled")

    def test_bad_input_is_refused_before_anything_runs(self):
        for body in ({"preset": "continents; calc"}, {"preset": "continents", "seed": "abc"}, {"preset": "continents", "seed": str(2 ** 64)},
                     {"code": "RNW1-AAAAA"}, {"code": "hello"}, {}):
            st, res, _ = self.post("/api/rnw/new", body)
            self.assertEqual(st, 400, body)
        self.assertIsNone(self.req("GET", "/api/rnw/job")[1]["job"])
        self.assertEqual(self.post("/api/rnw/add", {"id": "x&calc"})[0], 400)
        self.assertEqual(self.post("/api/rnw/remove", {"id": "x y"})[0], 400)
        self.assertEqual(self.post("/api/rnw/nope", {})[0], 400)

    def test_the_junk_the_generator_prints_is_an_error_not_a_crash(self):
        with mock.patch.dict(os.environ, {"RNW_STUB": "junk"}):
            st, res, _ = self.post("/api/rnw/new", {"preset": "continents"})
        self.assertEqual(st, 400)
        self.assertIn("could not make a code", res["error"])

    def test_adding_and_removing_a_world_by_id(self):
        self.assertEqual(self.post("/api/rnw/add", {"id": "kept000000"})[0], 200)
        self.assertEqual(self.wait()["state"], "done")
        self.assertTrue(list(self.mods_dir.glob("rnw_exp_world_*")))
        self.assertEqual(self.post("/api/rnw/remove", {"id": "kept000000"})[0], 200)
        self.assertFalse(list(self.mods_dir.glob("rnw_exp_world_*")))
        self.assertEqual(self.req("GET", "/api/rnw/list")[1]["worlds"], [])

    def test_a_world_that_lands_outside_the_mod_folder_is_explained(self):
        other = self.r / "elsewhere"
        other.mkdir()
        with mock.patch.dict(os.environ, {"RNW_STUB_MODS": str(other)}):
            self.post("/api/rnw/new", {"code": CODE})
            job = self.wait()
        self.assertIn("not the mod folder this app reads", job["error"])

    def test_the_user_points_to_a_folder_and_gets_a_report_back(self):
        self.mgr._generator = None
        d = self.r / "rnwhere"
        d.mkdir()
        res = self.post("/api/rnw/folder", {"path": str(self.r / "nowhere")})[1]   # not a folder
        self.assertFalse(res["ok"])
        self.assertIn("is not a folder", res["report"][0]["text"])
        res = self.post("/api/rnw/folder", {"path": str(d)})[1]   # a folder without Random New World
        self.assertEqual((res["ok"], res["generator"]), (False, None))
        self.assertIn("was not found there", res["report"][-1]["text"])
        self.assertEqual(self.app.store.settings()["rnw_dir"], "")
        (d / "rnw.cmd").write_text("x")
        res = self.post("/api/rnw/folder", {"path": f'"{d}"'})[1]   # Copy as path adds quotes
        self.assertTrue(res["ok"])
        self.assertEqual((res["generator"]["folder"], res["generator"]["how"]), (str(d), "the folder you chose"))
        self.assertEqual(res["report"][-1]["text"], "Ready: maps can be made from here.")
        self.assertEqual(self.app.store.settings()["rnw_dir"], str(d))
        self.assertEqual(self.mgr.generator().cmd, d / "rnw.cmd")
        self.assertFalse(self.post("/api/rnw/folder", {"path": ""})[1]["ok"])   # empty = forget
        self.assertEqual(self.app.store.settings()["rnw_dir"], "")

    def test_browse_asks_the_system_for_a_folder_without_the_lock(self):
        calls = []
        self.mgr.picker = lambda title, start: calls.append((title, start)) or {"path": str(self.r), "cancelled": False, "error": ""}
        res = self.post("/api/rnw/pick", {"what": "generator"})[1]
        self.assertEqual(res["path"], str(self.r))
        self.assertIn("Random New World is installed", calls[0][0])
        self.post("/api/rnw/pick", {"what": "map", "start": "x"})
        self.assertIn("map", calls[1][0])
        self.assertEqual(calls[1][1], "x")

    def test_the_app_does_not_search_the_disk_for_the_generator_but_suggests_the_workshop_folder(self):
        self.mgr._generator = None
        ws = self.ws() / "3829217331"
        ws.mkdir(parents=True, exist_ok=True)
        (ws / "rnw.cmd").write_text("x")
        self.assertIsNone(self.mgr.generator())   # it exists in the Workshop folder, but the user has not pointed to it
        res = self.req("GET", "/api/rnw/files")[1]
        self.assertIsNone(res["generator"])
        self.assertEqual(res["hint"], str(ws))

    def test_open_starts_only_the_launcher_without_a_shell(self):
        calls = []
        d = self.r / "g"
        d.mkdir()
        (d / "Random New World.exe").write_text("x")
        self.mgr._generator = rnw.inspect_folder(d)
        self.mgr.popen = lambda argv, **kw: calls.append((argv, kw))
        st, res, _ = self.post("/api/rnw/open", {})
        self.assertEqual(st, 200, res)
        self.assertEqual(calls[0][0], [str(d / "Random New World.exe")])
        self.assertNotIn("shell", calls[0][1])
        self.mgr._generator = rnw.Generator(d, prefix=["x"])
        self.assertEqual(self.post("/api/rnw/open", {})[0], 400)   # no launcher known

    def worlds_in_playset(self):
        mkmod(self.user(), "rnw_exp_world_aaaaa22222", "RNW: One", stub=False)
        mkmod(self.user(), "rnw_exp_world_bbbbb22222", "RNW: Two", stub=False)
        mkmod(self.user(), "Refined", "Refined Colonization", stub=False)
        mkworkshop(self.ws(), 3829217331, "Random New World")
        self.post("/api/rescan", {})
        ids = ["ws:3829217331", "local:Refined", "local:rnw_exp_world_aaaaa22222"]
        return self.new_playset(ids)

    def test_use_turns_one_world_on_the_rest_off_and_puts_it_last(self):
        pid = self.worlds_in_playset()
        st, res, _ = self.post("/api/rnw/use", {"playset": pid, "folder": "rnw_exp_world_bbbbb22222"})
        self.assertEqual(st, 200, res)
        ps = res["playset"]
        on = lambda p: [m for m in p["mods"] if m not in p["disabled"]]
        self.assertEqual(on(ps), ["local:Refined", "local:rnw_exp_world_bbbbb22222"])   # the world loads last
        self.assertEqual(set(ps["disabled"]), {"ws:3829217331", "local:rnw_exp_world_aaaaa22222"})
        self.assertTrue(any("NEW 1337 campaign" in line for line in res["did"]))
        # and back to the first one
        res = self.post("/api/rnw/use", {"playset": pid, "folder": "rnw_exp_world_aaaaa22222"})[1]
        self.assertEqual(on(res["playset"])[-1], "local:rnw_exp_world_aaaaa22222")
        self.assertIn("local:rnw_exp_world_bbbbb22222", res["playset"]["disabled"])
        self.assertNotIn("local:rnw_exp_world_aaaaa22222", res["playset"]["disabled"])
        # turn it off
        res = self.post("/api/rnw/use", {"playset": pid, "folder": "rnw_exp_world_aaaaa22222", "on": False})[1]
        self.assertIn("local:rnw_exp_world_aaaaa22222", res["playset"]["disabled"])

    def test_use_refuses_a_world_that_is_not_installed_and_an_unknown_playset(self):
        pid = self.new_playset([])
        st, res, _ = self.post("/api/rnw/use", {"playset": pid, "folder": "rnw_exp_world_zzzzz22222"})
        self.assertEqual(st, 400)
        self.assertIn("Add to game", res["error"])
        self.assertEqual(self.post("/api/rnw/use", {"playset": "nope", "folder": "x"})[0], 404)

    def test_the_list_says_which_worlds_are_on_in_the_active_playset(self):
        pid = self.worlds_in_playset()
        self.post(f"/api/playsets/{pid}/activate", {})
        self.post("/api/rnw/use", {"playset": pid, "folder": "rnw_exp_world_aaaaa22222"})
        res = self.req("GET", "/api/rnw/list")[1]
        state = {w["folder"]: w["in_playset"] for w in res["worlds"]}
        self.assertEqual(state, {"rnw_exp_world_aaaaa22222": "on", "rnw_exp_world_bbbbb22222": "none"})
        self.assertTrue(res["hub"]["installed"])
        self.assertFalse(res["hub"]["enabled"])


if __name__ == "__main__":
    unittest.main()
