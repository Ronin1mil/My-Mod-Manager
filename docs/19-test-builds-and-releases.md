# Test builds (nightly) and releases

Two channels, so that **a release only contains what was tried first**:

| | Test build ("nightly") | Release |
|---|---|---|
| Built from | the branch being worked on (`nightly`) | `main` |
| When | automatically on every push to that branch, after all checks pass | only when someone publishes (Actions -> CI -> Run workflow -> `publish`) |
| Where | one rolling prerelease with the fixed tag `test-build` (replaced on each build; a release needs a tag to hold the files, so there is exactly one, never one per build) | `vX.Y.Z` releases |
| Installed by | Settings -> App & updates -> **Test builds (nightly)** (experimental) | the update banner, or the Releases page |

## Flow
1. Work on the test branch and push. CI runs the unit tests, the browser tests, builds the Windows app and installer, and publishes them as the `nightly` prerelease. The release notes carry a line `build: <7-character commit id>`.
2. In the app, Settings -> App & updates -> *Check for a test build*, then *Install the test build*. The title bar area at the bottom left shows `vX.Y.Z · test <commit id>` while a test build is installed.
3. Try it. Fix what is wrong on the branch (each push replaces the test build).
4. When it is good, bring **that exact commit** to `main` (fast-forward merge), add the version and changelog section, and publish. The release job prints a warning if its commit is not the one the last test build was made from.

## How the app handles it
- A test build has a build id in `modmanager/_build.py`, written by CI only for the test branch (the file is not in git). Releases from `main` have none.
- The test build uses the same safety as a release update: the files come only from this repository's GitHub release `nightly`, and the SHA-256 listed in its `SHA256SUMS.txt` must match before the running app is replaced.
- A test build counts as *older than the release of its own version*, so once that release exists the normal update banner offers it. To leave the test channel earlier, press "Check for updates now".
- Your playsets and settings are not touched by switching channels.

## Activity log (for finding what is slow)
Test builds write `RoninModManager-activity.log` next to the error log (`Documents\Ronin Mod Manager\`). One line per event with a millisecond timestamp and the thread. A step that can take a while writes `>` when it starts and `<` with its duration when it ends, so a hang shows as a `>` with no `<`. It records start-up, every API request with its duration and status, reading the mod folders, the load-order check, the conflict scan (with counts), writing the load file, update checks and the update steps. It never records mod contents.

It is on for test builds and off in releases; set the environment variable `MODMANAGER_ACTIVITY_LOG=1` (or `0`) to force it either way. Send the file when something feels slow.
