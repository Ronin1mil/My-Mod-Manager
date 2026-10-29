# Releasing

1. Bump `__version__` in `modmanager/__init__.py`.
2. Add a section at the top of `CHANGELOG.md`: `## X.Y.Z - short title`, then **a short summary for people reading the Releases page**, then the details as bullets.
   - A feature release (X.Y.0): one to three sentences on what changed most.
   - A patch release (X.Y.Z): one sentence.
3. Push to `main`, wait for CI to pass, then start the **CI** workflow by hand (Actions → CI → Run workflow) with **publish** ticked. It builds the apps and installer, creates the tag `vX.Y.Z` and publishes the release.
   (Pushing a `vX.Y.Z` tag also publishes, as long as the tag equals the version in `__init__.py`.)

The release title and the notes shown on the Releases page are taken from that CHANGELOG section by `.github/scripts/release-notes.sh`. **The release job fails if the version has no section**, so a release cannot go out without notes.

To fix wording of releases that already exist, edit `CHANGELOG.md`, push, and run the workflow with **refresh_notes** ticked: it rewrites the title and notes of every release that has a changelog section.

## macOS and Linux builds (saved for later)
Releases contain Windows files only. The `build` matrix in `.github/workflows/ci.yml` keeps the Linux and macOS entries as a comment; paste them back to build `Mod-Manager-linux` and `Mod-Manager-macos` again (they were building before, the macOS runner was sometimes unavailable). Unit tests still run on Ubuntu and Windows.
