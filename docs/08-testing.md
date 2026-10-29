# Testing

Everything below runs without a game, Steam or network. **Nothing here proves the game accepts what we write**; that needs a real install (docs/13).

## Run
```bash
python -m unittest discover -s tests -t .                       # 244 tests, ~8 s; Python 3.8-3.13 (CI) - also run locally on 3.11/3.12/3.13
npm i --no-save playwright && npx playwright install chromium
for t in ui order compare games; do node tests/e2e/$t.mjs; done  # browser end-to-end
GAME=ck3 node tests/e2e/ui.mjs                                   # the same flow on CK3 (default VIC3)
```
`tests/__init__.py` points `MODMANAGER_CONFIG_DIR` at a throwaway folder, and each server test uses its own, so no test touches your real config or Steam.

## Unit and API tests (`tests/`)
| File | Covers |
|---|---|
| `test_games.py` | the game registry's pinned facts (app ids, load files/styles, markers), themes complete, nothing marked verified |
| `test_detect.py` | installs in any library for **each game**, other games not mistaken, pasted deep paths, renamed folders, `libraryfolders.vdf`, versions, user dirs, config dir, logos (per game, size/type limits, Steam cache by app id, fetch validation) |
| `test_scan_games.py` | metadata in all three locations and both relationship spellings, ids beating renamed names, damaged/odd metadata, descriptors, conflicts in CK3-style and EU5-style layouts, categories, REPLACE/INJECT, replace_path, localization, symlinks, **base-game comparison** (flags, 3-way clash is not "vanilla", lazy parsing) |
| `test_store_games.py` | per-game load files (descriptor vs path style, Workshop stubs, backup, damaged file), store validation, rolling backup, damaged file never overwritten, share round-trip, workshop-id-over-name, cross-game refusal, **legacy share formats**, hostile documents, **migration from the standalone managers**, global settings |
| `test_presets.py` | preset validation (hostile fields, ids that could escape the folder), user/built-in loading, apply with missing mods, save-as-preset, the draft RICE preset is labelled unverified; `workshop.py` with a fake `steamcmd` runner (exact argv, no shell, failures per item, timeouts, "Success" text without the folder not trusted, one job at a time); the HTTP endpoints |
| `test_multigame.py` | one server, all games: state, load order, launch writes the right file and asks Steam for the right app id, games are isolated, share/import across games, unknown games/routes, bulk actions, static files/headers, Host/Origin checks, setup flow (pasted path, wrong game's install, first-boot detection, Workshop folder follows the library, base-game toggle), logo route |
| `test_launch.py` | **stub game** for every game: a fake executable records its argv, cwd and the load file it sees |
| `test_core.py`, `test_order.py`, `test_order_property.py`, `test_compare.py`, `test_library.py`, `test_install.py`, `test_saves.py`, `test_update.py`, `test_fuzz.py`, `test_server.py` | carried over from the VIC3 manager and adapted: parsers, order engine (seeded random graphs: permutation, dependencies satisfied, idempotent, valid order untouched, cycles, 3000-deep chain), LIS-based compare, library tracking, safe install (zip-slip, bombs, symlinks, executables), save links (backup-first), update checker (fake GitHub, off by default, no request unless enabled), fuzzing of every parser and 400 mutated zips, HTTP hardening (413, bad Host/Origin, parallel clients) |

## Browser end-to-end (`tests/e2e/`, Playwright + Chromium)
- `ui.mjs` add a mod, hit the dependency problem, one-click fix, "why is it here", conflict, install a zip, reject a hostile launch argument, press Play against the stub, headers/Host handling. Runs for VIC3 and CK3.
- `order.mjs` drag and drop with auto-sort on and off, arrows, Sort now, enable/disable, fix, remove/re-add, drawer, persistence, independent playsets.
- `compare.mjs` Compare tab actions, Settings dialog (update check off by default), hostile update payload rendered inert, banner dismissal per version.
- `games.mjs` **all three games through the UI only**: setup dialog finds each install from a deep pasted path, Workshop folder derived, library/conflicts/order per game's folders, Play writes each game's own load file, per-game accent colours, last game remembered, RICE preset (unverified label, create playset, not-installed list, Open in Steam, no steamcmd button when unconfigured).

## What the tests found while porting (all fixed)
- Zip install still posted to the old un-prefixed URL after routing became per-game (found by `ui.mjs`).
- A conflict involving the base game *and two mods* was labelled "base game" and hid the real mod-vs-mod clash (found by the first browser screenshot, then pinned by `BaseGameComparison`).
- `python -m modmanager` worked but the PyInstaller entry would not: relative imports in `__main__.py` (found while writing CI; absolute imports now).
- Tests that read a non-hermetic config folder (fixed with `MODMANAGER_CONFIG_DIR`).

## Not tested (needs a real install or a real machine)
Real game start, whether the stock launcher overrides the load file, EU5's load file format, junction handling on Windows, the Windows `.exe`, real `steamcmd`, the update check against the real repository, a Steam client handling `steam://url/CommunityFilePage/<id>`.
