import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OLD = re.compile(r"test[ _]builds?\b", re.I)   # the retired name; the GitHub tag `test-build` (hyphen) is the one allowed leftover


class Naming(unittest.TestCase):
    """Official versions are "Version X.Y.Z"; in-between ones are "nightly builds". The old name must not come back (docs/19)."""

    def files(self):
        for pat in ("modmanager/**/*.py", "modmanager/static/*", ".github/workflows/*.yml", ".github/scripts/*", "CHANGELOG.md", "README.md"):
            yield from (p for p in ROOT.glob(pat) if p.is_file())

    def test_the_retired_name_is_not_used_in_the_app_ci_changelog_or_readme(self):
        bad = [f"{p.relative_to(ROOT)}:{n}: {line.strip()[:100]}" for p in self.files()
               for n, line in enumerate(p.read_text(encoding="utf-8", errors="replace").splitlines(), 1) if OLD.search(line)]
        self.assertEqual(bad, [])


if __name__ == "__main__":
    unittest.main()
