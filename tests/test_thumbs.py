"""A mod's own picture: found in the mod folder only, served by the app, never followed through a link."""
import http.client
import os
import tempfile
import unittest
from pathlib import Path

from modmanager import games, thumbs
from tests import helpers
from tests.helpers import mkmod

PNG = b"\x89PNG\r\n\x1a\n" + b"0" * 40


class Find(unittest.TestCase):
    def setUp(self):
        self.d = Path(tempfile.mkdtemp())

    def test_none_without_a_picture(self):
        self.assertIsNone(thumbs.find(self.d))
        self.assertIsNone(thumbs.find(""))

    def test_thumbnail_in_the_mod_folder_or_metadata(self):
        (self.d / ".metadata").mkdir()
        (self.d / ".metadata/thumbnail.jpg").write_bytes(b"x" * 10)
        self.assertEqual(thumbs.find(self.d).name, "thumbnail.jpg")
        (self.d / "thumbnail.png").write_bytes(PNG)
        self.assertEqual(thumbs.find(self.d), self.d / "thumbnail.png")   # the mod folder comes first

    def test_other_names_and_types(self):
        (self.d / "preview.webp").write_bytes(b"x" * 10)
        self.assertEqual(thumbs.find(self.d).name, "preview.webp")

    def test_unknown_type_empty_and_huge_files_are_ignored(self):
        (self.d / "thumbnail.bmp").write_bytes(b"x" * 10)
        (self.d / "preview.png").write_bytes(b"")
        with open(self.d / "cover.png", "wb") as f:
            f.truncate(thumbs.MAX_BYTES + 1)
        self.assertIsNone(thumbs.find(self.d))

    @unittest.skipUnless(hasattr(os, "symlink"), "needs symlinks")
    def test_a_link_is_not_followed(self):
        other = self.d / "secret.png"
        other.write_bytes(PNG)
        mod = self.d / "mod"
        mod.mkdir()
        try:
            os.symlink(other, mod / "thumbnail.png")
        except OSError:
            self.skipTest("cannot make links here")
        self.assertIsNone(thumbs.find(mod))


class Served(helpers.GameCase):
    GAME = games.CK3

    def test_a_mods_picture_is_served_and_others_get_404(self):
        with_pic = mkmod(self.user(), "Pic", "Pic")
        (with_pic / "thumbnail.png").write_bytes(PNG)
        mkmod(self.user(), "Bare", "Bare")
        self.post("/api/rescan")
        st, body, r = self.req("GET", "/api/thumb/local%3APic")
        self.assertEqual((st, body, r.getheader("Content-Type")), (200, PNG, "image/png"))
        self.assertEqual(self.req("GET", "/api/thumb/local%3ABare")[0], 204)
        self.assertEqual(self.req("GET", "/api/thumb/local%3ANope")[0], 204)

    def test_etag_gives_304_and_a_foreign_host_is_refused(self):
        (mkmod(self.user(), "Pic", "Pic") / "thumbnail.png").write_bytes(PNG)
        self.post("/api/rescan")
        tag = self.req("GET", "/api/thumb/local%3APic")[2].getheader("ETag")
        self.assertEqual(self.req("GET", "/api/thumb/local%3APic", headers={"If-None-Match": tag})[0], 304)
        self.assertEqual(self.req("GET", "/api/thumb/local%3APic", headers={"Host": "evil.example"})[0], 403)


if __name__ == "__main__":
    unittest.main()


class UnreadFolders(unittest.TestCase):
    def test_empty_and_unreadable_workshop_folders_are_listed(self):
        from modmanager import scan
        root = Path(tempfile.mkdtemp())
        (root / "111").mkdir()                                      # Steam has not downloaded it
        (root / "222").mkdir(); (root / "222" / "notes.txt").write_text("x")   # files, but no descriptor or metadata
        (root / "333" / ".metadata").mkdir(parents=True); (root / "333" / ".metadata" / "metadata.json").write_text('{"name": "ok"}')
        mods = scan.scan_mods(None, root)
        self.assertEqual(list(mods), ["ws:333"])
        got = {u["id"]: u for u in scan.unread_folders(root, mods)}
        self.assertEqual(set(got), {"111", "222"})
        self.assertTrue(got["111"]["empty"])
        self.assertEqual(got["222"]["files"], ["notes.txt"])

    def test_a_folder_read_through_a_mod_file_is_not_reported(self):
        from modmanager import scan
        root = Path(tempfile.mkdtemp())
        (root / "444").mkdir(); (root / "444" / "common").mkdir()
        mods = {"local:ugc_444": {"root": str(root / "444")}}
        self.assertEqual(scan.unread_folders(root, mods), [])

    def test_a_descriptor_with_the_mods_own_name_is_read(self):
        from modmanager import scan
        root = Path(tempfile.mkdtemp())
        d = root / "555"; d.mkdir(); (d / "Cool_Mod.mod").write_text('name="Cool Mod"\nversion="1.0"\n'); (d / "common").mkdir()
        mods = scan.scan_mods(None, root)
        self.assertEqual(mods["ws:555"]["name"], "Cool Mod")
        self.assertEqual(scan.unread_folders(root, mods), [])
        (root / "666").mkdir(); (root / "666" / "a.mod").write_text('name="A"'); (root / "666" / "b.mod").write_text('name="B"')
        self.assertNotIn("ws:666", scan.scan_mods(None, root))   # two candidates: not guessed
