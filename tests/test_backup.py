"""Backup and restore of the app's own data (Settings > App)."""
import io
import json
import tempfile
import unittest
import zipfile
from pathlib import Path

from modmanager import backup, games
from modmanager.library import Library
from modmanager.store import Store
from tests.helpers import GameCase


def zipped(files, manifest=True, version=1):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        if manifest:
            z.writestr("backup.json", json.dumps({"format": backup.FORMAT, "version": version}))
        for k, v in files.items():
            z.writestr(k, v if isinstance(v, (str, bytes)) else json.dumps(v))
    return buf.getvalue()


class Files(unittest.TestCase):
    def setUp(self):
        t = tempfile.TemporaryDirectory()
        self.addCleanup(t.cleanup)
        self.base = Path(t.name) / "cfg"
        (self.base / "ck3/presets").mkdir(parents=True)
        (self.base / "ck3/backups/old-mod").mkdir(parents=True)
        (self.base / "ck3/backups/old-mod/x.txt").write_text("big mod files stay out")
        (self.base / "settings.json").write_text(json.dumps({"last_game": "ck3"}))
        s = Store(self.base / "ck3/playsets.json")
        self.pid = s.create("Main", ["a"])
        (self.base / "ck3/library.json").write_text(json.dumps({"mods": {}}))
        (self.base / "ck3/presets/mine.json").write_text(json.dumps({"id": "mine"}))
        (self.base / "parse-cache.json.gz").write_bytes(b"cache")

    def test_a_backup_holds_settings_playsets_library_and_presets_only(self):
        data, names = backup.make(self.base)
        self.assertEqual(sorted(names), ["ck3/library.json", "ck3/playsets.json", "ck3/presets/mine.json", "settings.json"])
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            self.assertEqual(json.loads(z.read("backup.json"))["format"], backup.FORMAT)

    def test_restore_puts_the_data_back_and_keeps_a_safety_copy(self):
        data, _ = backup.make(self.base)
        s = Store(self.base / "ck3/playsets.json")
        s.update(self.pid, name="Changed later")
        (self.base / "eu5").mkdir()
        (self.base / "eu5/playsets.json").write_text(json.dumps({"active": None, "playsets": {}}))
        res = backup.restore(self.base, data)
        self.assertEqual(Store(self.base / "ck3/playsets.json").get(self.pid)["name"], "Main")
        self.assertTrue((self.base / "eu5/playsets.json").is_file(), "a game that is not in the backup is left alone")
        safety = Path(res["safety_copy"])
        self.assertTrue(safety.is_file() and safety.parent.name == "app-backups")
        backup.restore(self.base, safety.read_bytes())   # the safety copy undoes the restore
        self.assertEqual(Store(self.base / "ck3/playsets.json").get(self.pid)["name"], "Changed later")

    def test_bad_backups_are_refused_and_nothing_is_written(self):
        before = (self.base / "ck3/playsets.json").read_text()
        cases = {
            "not a zip": b"hello",
            "no manifest": zipped({"settings.json": {}}, manifest=False),
            "newer": zipped({}, version=2),
            "escape": zipped({"../evil.json": {}}),
            "other file": zipped({"ck3/backups/x.json": {}}),
            "script": zipped({"ck3/presets/run.py": "print(1)"}),
            "not json": zipped({"ck3/playsets.json": "{nope"}),
            "not an object": zipped({"settings.json": [1, 2]}),
            "not playsets": zipped({"ck3/playsets.json": {"playsets": [1]}}),
        }
        for why, data in cases.items():
            with self.assertRaises(backup.BadBackup, msg=why):
                backup.restore(self.base, data)
        self.assertEqual((self.base / "ck3/playsets.json").read_text(), before)
        self.assertFalse((self.base / "app-backups").exists())


class OverHttp(GameCase):
    GAME = games.CK3

    def kw(self, g):   # the real app's layout: every game's data in the config folder
        k = super().kw(g)
        return {**k, "store": Store(game=g), "library": Library(self.r / "cfg" / g.id / "library.json")}

    def test_download_then_restore_brings_back_the_playsets(self):
        pid = self.new_playset([])
        st, data, r = self.req("GET", "/api/backup")
        self.assertEqual(st, 200)
        self.assertEqual(r.getheader("Content-Type"), "application/zip")
        self.assertIn("attachment; filename=\"RoninModManager-backup-", r.getheader("Content-Disposition"))
        self.post(f"/api/playsets/{pid}/delete")
        self.assertEqual(self.req("GET", "/api/state")[1]["playsets"], [])
        st, res, _ = self.req("POST", "/api/restore-backup", raw=data, headers={"Content-Type": "application/zip"})
        self.assertEqual(st, 200, res)
        self.assertIn("ck3/playsets.json", res["restored"])
        self.assertEqual([p["id"] for p in self.req("GET", "/api/state")[1]["playsets"]], [pid])

    def test_an_old_game_object_can_no_longer_write_over_restored_files(self):
        pid = self.new_playset([])
        self.post(f"/api/playsets/{pid}/update", {"name": "Kept"})
        data = self.req("GET", "/api/backup")[1]
        old = self.hub.app("ck3")
        self.post(f"/api/playsets/{pid}/delete")
        self.assertEqual(self.req("POST", "/api/restore-backup", raw=data)[0], 200)
        old.store.data["playsets"].clear()   # a request that started before the restore finishes on the old object
        old.store.save()
        old.library.save()
        self.assertEqual([p["name"] for p in self.req("GET", "/api/state")[1]["playsets"]], ["Kept"])
        self.assertIsNot(self.hub.app("ck3"), old)

    def test_a_bad_file_or_another_website_is_refused(self):
        st, res, _ = self.req("POST", "/api/restore-backup", raw=b"not a zip")
        self.assertEqual(st, 400)
        self.assertIn("not a Ronin Mod Manager backup", res["error"])
        self.assertEqual(self.req("POST", "/api/restore-backup", raw=zipped({}), headers={"Origin": "http://evil.example"})[0], 403)
        self.assertEqual(self.req("GET", "/api/backup", headers={"Sec-Fetch-Site": "cross-site"})[0], 403)


if __name__ == "__main__":
    unittest.main()
