import os
import time
import unittest
from pathlib import Path

from modmanager import crash, games
from tests.helpers import GameCase, mkmod, mkworkshop

ERROR_LOG = """\
[12:00:00][game.cpp:10]: Loading game
[12:00:01][jomini_script.cpp:11]: Error: unexpected token in file: mod/Brokemod/common/traits/x.txt line: 10
[12:00:01][jomini_script.cpp:11]: Error: unexpected token in file: mod/Brokemod/common/traits/y.txt line: 22
[12:00:02][jomini_script.cpp:11]: Warning: missing key in file: mod/Quietmod/common/a.txt line: 3
[12:00:03][jomini_script.cpp:11]: Error: bad value C:/Games/steamapps/workshop/content/1158310/3705667883/events/e.txt line: 7
[12:00:04][pdx_gui.cpp:5]: Something harmless happened
[12:00:05][crash.cpp:1]: EXCEPTION_ACCESS_VIOLATION at 0x7ff
"""


def mod(mid, name, root, rid=None):
    return {"id": mid, "name": name, "root": root, "remote_id": rid, "exists": True, "dependencies": []}


class Analyse(unittest.TestCase):
    def setUp(self):
        import tempfile
        self.td = tempfile.TemporaryDirectory()
        self.addCleanup(self.td.cleanup)
        self.u = Path(self.td.name)
        (self.u / "logs").mkdir()
        (self.u / "logs/error.log").write_text(ERROR_LOG)
        self.mods = {m["id"]: m for m in (mod("local:Brokemod", "Broke Mod", "/u/mod/Brokemod"),
                                          mod("local:Quietmod", "Quiet Mod", "/u/mod/Quietmod"),
                                          mod("local:Other", "Other Mod", "/u/mod/Other"),
                                          mod("workshop:3705667883", "Workshop Thing", "/w/3705667883", "3705667883"))}

    def run_analysis(self, enabled=None, issues=(), changed=None, files=None):
        enabled = enabled or list(self.mods)
        return crash.analyse(games.CK3, self.mods, enabled, list(issues), changed or {},
                             files if files is not None else crash.log_files(games.CK3, self.u))

    def test_mod_named_in_error_lines_comes_first(self):
        r = self.run_analysis()
        self.assertEqual(r["suspects"][0]["id"], "local:Brokemod")
        self.assertEqual(r["suspects"][0]["errors"], 2)
        self.assertTrue(r["suspects"][0]["samples"])
        self.assertIn("local:Quietmod", [s["id"] for s in r["suspects"]])   # a warning counts, but less
        self.assertGreater(r["suspects"][0]["score"], r["suspects"][1]["score"])

    def test_workshop_id_in_a_path_names_the_mod(self):
        r = self.run_analysis()
        self.assertIn("workshop:3705667883", [s["id"] for s in r["suspects"]])

    def test_mods_the_logs_do_not_name_are_not_blamed(self):
        r = self.run_analysis()
        self.assertNotIn("local:Other", [s["id"] for s in r["suspects"]])

    def test_disabled_mods_are_ignored(self):
        r = self.run_analysis(enabled=["local:Other", "local:Quietmod"])
        self.assertNotIn("local:Brokemod", [s["id"] for s in r["suspects"]])

    def test_known_crash_signature_is_named(self):
        r = self.run_analysis()
        self.assertEqual([x["kind"] for x in r["reasons"]], ["access"])
        self.assertIn("EXCEPTION_ACCESS_VIOLATION", r["reasons"][0]["evidence"])

    def test_out_of_memory_and_driver_are_recognised(self):
        (self.u / "logs/game.log").write_text("std::bad_alloc\nDXGI_ERROR_DEVICE_REMOVED\n")
        kinds = {x["kind"] for x in self.run_analysis()["reasons"]}
        self.assertTrue({"memory", "gpu"} <= kinds)

    def test_missing_assembly_is_named(self):
        (self.u / "logs/game.log").write_text("System.IO.FileNotFoundException: Could not load file or assembly 'Bannerlord.Harmony, Version=2' or one of its dependencies\n")
        r = self.run_analysis()
        a = [x for x in r["reasons"] if x["kind"] == "assembly"]
        self.assertTrue(a and "Bannerlord.Harmony" in a[0]["title"])

    def test_the_apps_own_findings_count(self):
        (self.u / "logs/error.log").write_text("nothing here\n")
        issue = {"severity": "error", "code": "missing_dependency", "module": "local:Other", "message": "Other Mod needs Lib, which is not installed."}
        r = self.run_analysis(issues=[issue])
        self.assertEqual(r["suspects"][0]["id"], "local:Other")
        self.assertIn("needs Lib", r["suspects"][0]["why"][0])
        self.assertFalse(r["suspects"][0]["in_logs"])

    def test_recently_changed_mods_are_listed_low(self):
        (self.u / "logs/error.log").write_text("nothing here\n")
        r = self.run_analysis(changed={"local:Other": "updated since the app last looked at your mods"})
        self.assertEqual(r["suspects"][0]["id"], "local:Other")
        self.assertEqual(r["suspects"][0]["level"], "low")

    def test_clear_leader_is_high_confidence(self):
        (self.u / "logs/error.log").write_text(ERROR_LOG * 1 + "".join(
            f"[1][a.cpp:1]: Error: bad thing {n} in mod/Brokemod/common/f{n}.txt\n" for n in range(6)))
        r = self.run_analysis()
        self.assertEqual(r["suspects"][0]["level"], "high")

    def test_newest_crash_folder_is_read(self):
        old, new = self.u / "crashes/2026-01-01", self.u / "crashes/2026-02-02"
        for d, text in ((old, "mod/Other/x.txt Error old"), (new, "Error in mod/Other/common/y.txt")):
            d.mkdir(parents=True)
            (d / "exception.txt").write_text(text)
        os.utime(old, (time.time() - 5000, time.time() - 5000))
        files = crash.log_files(games.CK3, self.u)
        self.assertIn(str(new), {str(f["path"].parent) for f in files})
        self.assertNotIn(str(old), {str(f["path"].parent) for f in files})

    def test_no_logs_says_so(self):
        r = self.run_analysis(files=[])
        self.assertEqual(r["suspects"], [])
        self.assertIn("No game logs were found", r["notes"][0])

    def test_logs_that_name_nothing_suggest_halving(self):
        (self.u / "logs/error.log").write_text("all fine\n")
        r = self.run_analysis()
        self.assertIn("halving", " ".join(r["notes"]))

    def test_user_name_is_not_shown(self):
        user = Path.home().name
        if len(user) < 3 or user.lower() in ("root", "user", "admin"):
            self.skipTest("this PC's user name is generic")
        (self.u / "logs/error.log").write_text(f"Error in C:/Users/{user}/Documents/mod/Brokemod/x.txt\n")
        r = self.run_analysis()
        self.assertNotIn(user, " ".join(r["suspects"][0]["samples"]))

    def test_bannerlord_reads_programdata_logs(self):
        pd = self.u / "ProgramData"
        (pd / games.BANNERLORD.user_dir_name / "logs").mkdir(parents=True)
        (pd / games.BANNERLORD.user_dir_name / "logs/rgl_log_errors_1.txt").write_text("Exception in Modules/Brokemod/bin/x.dll\n")
        files = crash.log_files(games.BANNERLORD, self.u / "docs", programdata=str(pd))
        self.assertEqual([f["path"].name for f in files], ["rgl_log_errors_1.txt"])

    def test_html_crash_report_is_reduced_to_text(self):
        (self.u / "logs/error.log").unlink()
        (self.u / "logs/report.html").write_text("<html><body><p>Unhandled exception</p><div>at Modules/Brokemod/x</div></body></html>")
        lines = crash.read_tail(self.u / "logs/report.html")
        self.assertIn("Unhandled exception", lines)


class Route(GameCase):
    GAME = games.CK3

    def test_diagnose_route_ranks_the_mod_named_in_the_log(self):
        u = self.user()
        mkmod(u, "Brokemod")
        mkmod(u, "Fine")
        mkworkshop(self.ws(), 3705667883, "Workshop Thing")
        self.post("/api/rescan", {})
        pid = self.new_playset(["local:Brokemod", "local:Fine", "workshop:3705667883"])
        (u / "logs").mkdir()
        (u / "logs/error.log").write_text(ERROR_LOG)
        st, res, _ = self.req("GET", f"/api/crash/{pid}")
        self.assertEqual(st, 200)
        self.assertEqual(res["suspects"][0]["id"], "local:Brokemod")
        self.assertEqual(res["reasons"][0]["kind"], "access")
        self.assertEqual(res["logs"][0]["name"], "error.log")

    def test_unknown_playset_is_404(self):
        self.assertEqual(self.req("GET", "/api/crash/nope")[0], 404)


if __name__ == "__main__":
    unittest.main()
