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
