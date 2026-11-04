# Nightly builds and releases

## What things are called (a rule, not a suggestion)
- An official release is **Version X.Y.Z** (for example "Version 1.0.7"). Never "test", "preview", "beta build" or any other label.
- An in-between version made from the `nightly` branch is a **nightly build**, named only by its build id (the short commit id,
  for example "nightly build 380cdcf"). Nothing else is invented: no code names, no extra titles.
- The words "test build" are not used anywhere: not in the app, the release page, the docs, the changelog or the messages.
  Releases are not tests; they are official versions with official numbers, and the nightly builds are separate from them.
- The one thing that still says `test-build` is the GitHub tag that holds the rolling nightly build. Copies already installed
  look that tag up to find nightly builds, so renaming it would break their update check. The app never shows it.

Two channels, so that **a release only contains what was tried first**:

| | Nightly build ("nightly") | Release |
|---|---|---|
| Built from | the branch being worked on (`nightly`) | `main` |
| When | automatically on every push to that branch, after all checks pass | only when someone publishes (Actions -> CI -> Run workflow -> `publish`) |
| Where | one rolling prerelease with the fixed tag `test-build` (replaced on each build; a release needs a tag to hold the files, so there is exactly one, never one per build) | `vX.Y.Z` releases |
| Installed by | Settings -> App & updates -> **Nightly builds** (experimental) | the update banner, or the Releases page |

## Flow
1. Work on the test branch and push. CI runs the unit tests, the browser tests, builds the Windows app and installer, and publishes them as the `nightly` prerelease. The release notes carry a line `build: <7-character commit id>`.
2. In the app, Settings -> App & updates -> *Check for a nightly build*, then *Install the nightly build*. The title bar area at the bottom left shows `vX.Y.Z · test <commit id>` while a nightly build is installed.
3. Try it. Fix what is wrong on the branch (each push replaces the nightly build).
4. When it is good, bring **that exact commit** to `main` (fast-forward merge), add the version and changelog section, and publish. The release job prints a warning if its commit is not the one the last nightly build was made from.

## How the app handles it
- A nightly build has a build id in `modmanager/_build.py`, written by CI only for the test branch (the file is not in git). Releases from `main` have none.
- The nightly build uses the same safety as a release update: the files come only from this repository's GitHub release `nightly`, and the SHA-256 listed in its `SHA256SUMS.txt` must match before the running app is replaced.
- A copy running a nightly build is offered the newest **official release** first, whenever that release has a higher version number than the copy (banner and Tools -> Check for updates say "Version X.Y.Z"). Only when no higher release exists is it offered a newer nightly build ("nightly build <id>"). A nightly build of version 1.0.7 is never pushed back to the release 1.0.7: that release is what it was made into.
- Your playsets and settings are not touched by switching channels.

## Activity log (for finding what is slow)
Nightly builds write `RoninModManager-activity.log` next to the error log (`Documents\Ronin Mod Manager\`). One line per event with a millisecond timestamp and the thread. A step that can take a while writes `>` when it starts and `<` with its duration when it ends, so a hang shows as a `>` with no `<`. It records start-up, every API request with its duration and status, reading the mod folders, the load-order check, the conflict scan (with counts), writing the load file, update checks and the update steps. It never records mod contents.

It is on for nightly builds and off in releases; set the environment variable `MODMANAGER_ACTIVITY_LOG=1` (or `0`) to force it either way. Send the file when something feels slow.
