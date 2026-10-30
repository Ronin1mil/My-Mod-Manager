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

    def test_real_folder_is_set_aside_not_deleted(self):
        self.game.mkdir(parents=True)
        (self.game / "mine.v3").write_text("precious")
        res = saves.activate(self.game, self.a)
        self.assertEqual(res, f"linked_after_moving:{saves.shared_dir(self.game)}")
        self.assertEqual((saves.shared_dir(self.game) / "mine.v3").read_text(), "precious")
        # a real folder appearing while the shared one is kept does not overwrite it: it gets a backup name
        saves._remove_link(self.game)
        self.game.mkdir()
        (self.game / "newer.v3").write_text("2")
        res2 = saves.activate(self.game, self.a)
        self.assertTrue(res2.startswith("linked_after_backup:"), res2)
        self.assertTrue((saves.shared_dir(self.game) / "mine.v3").is_file())
        self.assertTrue((Path(res2.split(":", 1)[1]) / "newer.v3").is_file())

    def test_empty_real_folder_is_replaced(self):
        self.game.mkdir(parents=True)
        self.assertEqual(saves.activate(self.game, self.a), "linked")

    def test_file_in_the_way_is_refused(self):
        self.game.parent.mkdir(parents=True)
        self.game.write_text("x")
        with self.assertRaises(ValueError):
            saves.activate(self.game, self.a)


class PerPlaysetSaves(unittest.TestCase):
    """Runs on Windows too (NTFS junctions need no admin rights): the game's own saves stay with one playset and every
    other playset only ever sees its own."""

    def setUp(self):
        t = tempfile.TemporaryDirectory()
        self.addCleanup(t.cleanup)
        self.r = Path(t.name)
        self.game = self.r / "user/save games"
        self.managed = self.r / "cfg/saves"
        self.game.mkdir(parents=True)
        for n in ("old1.ck3", "old2.ck3"):
            (self.game / n).write_text(n)

    def names(self):
        return sorted(p.name for p in self.game.iterdir())

    def test_switching_playsets_shows_only_their_saves_and_the_games_own_come_back(self):
        pod, other = self.managed / "pod", self.managed / "other"
        saves.activate(self.game, pod)
        self.assertEqual(self.names(), [])                                  # Prince of Darkness: none of the old saves
        (self.game / "pod.ck3").write_text("pod")                           # the game saves into the playset's folder
        self.assertEqual((pod / "pod.ck3").read_text(), "pod")
        self.assertEqual(saves.activate(self.game, other), "linked")
        self.assertEqual(self.names(), [])
        saves.activate(self.game, pod)
        self.assertEqual(self.names(), ["pod.ck3"])
        self.assertTrue(saves.deactivate(self.game, self.managed).startswith("unlinked:"))
        self.assertFalse(saves.is_link(self.game))
        self.assertEqual(self.names(), ["old1.ck3", "old2.ck3"])           # the default playset: the game's own saves
        self.assertFalse(saves.shared_dir(self.game).exists())
        self.assertEqual((pod / "pod.ck3").read_text(), "pod")              # and the playset's saves are still there

    def test_an_interrupted_switch_is_repaired_on_the_next_shared_start(self):
        saves.activate(self.game, self.managed / "pod")
        saves._remove_link(self.game)                                       # the app stopped between the two steps
        self.assertEqual(saves.deactivate(self.game, self.managed), "restored")
        self.assertEqual(self.names(), ["old1.ck3", "old2.ck3"])

    def test_an_empty_folder_the_game_made_meanwhile_does_not_hide_the_kept_saves(self):
        saves.activate(self.game, self.managed / "pod")
        saves._remove_link(self.game)
        self.game.mkdir()                                                   # the game started without the app and made one
        self.assertEqual(saves.activate(self.game, self.managed / "pod"), "linked")
        saves.deactivate(self.game, self.managed)
        self.assertEqual(self.names(), ["old1.ck3", "old2.ck3"])


if __name__ == "__main__":
    unittest.main()
