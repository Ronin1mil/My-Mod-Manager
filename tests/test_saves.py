import os
import tempfile
import unittest
from pathlib import Path

from modmanager import saves


@unittest.skipIf(os.name == "nt", "symlink behaviour is covered by the junction path on Windows CI")
class T(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.r = Path(self.tmp.name)
        self.game = self.r / "user/save games"
        self.a, self.b = self.r / "a", self.r / "b"

    def tearDown(self):
        self.tmp.cleanup()

    def test_missing_folder_gets_linked_and_switching_keeps_both(self):
        self.assertEqual(saves.activate(self.game, self.a), "linked")
        (self.game / "one.v3").write_text("1")
        self.assertEqual(saves.activate(self.game, self.a), "already")
        self.assertEqual(saves.activate(self.game, self.b), "linked")
        self.assertEqual(list(self.game.iterdir()), [])
        self.assertEqual((self.a / "one.v3").read_text(), "1")  # switching never loses saves

    def test_real_folder_is_backed_up_not_deleted(self):
        self.game.mkdir(parents=True)
        (self.game / "mine.v3").write_text("precious")
        res = saves.activate(self.game, self.a)
        self.assertTrue(res.startswith("linked_after_backup:"))
        self.assertEqual((Path(res.split(":", 1)[1]) / "mine.v3").read_text(), "precious")
        # a second backup does not overwrite the first
        saves._remove_link(self.game)
        self.game.mkdir()
        (self.game / "newer.v3").write_text("2")
        res2 = saves.activate(self.game, self.a)
        self.assertNotEqual(res, res2)
        self.assertTrue((Path(res.split(":", 1)[1]) / "mine.v3").is_file())

    def test_empty_real_folder_is_replaced(self):
        self.game.mkdir(parents=True)
        self.assertEqual(saves.activate(self.game, self.a), "linked")

    def test_file_in_the_way_is_refused(self):
        self.game.parent.mkdir(parents=True)
        self.game.write_text("x")
        with self.assertRaises(ValueError):
            saves.activate(self.game, self.a)


if __name__ == "__main__":
    unittest.main()
