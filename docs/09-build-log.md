# Build log

A record of how the three managers became one, what was verified, and what was not.

## Starting point (2026-10-29)
| Repository | State |
|---|---|
| `ck3-mod-manager` | Python prototype `ck3mm` (scan, playsets, drag-and-drop, file/definition conflicts, web UI), 87 tests, plus planning docs for an unapproved Tauri/Rust rewrite; bundled a Paradox logo |
| `eu5-mod-manager` | Python `eu5mm`: install detection + setup dialog, base-game comparison, `REPLACE:`/`INJECT:` aware conflicts, localization conflicts, sharing, 52 tests; explicitly "written without access to the game" |
| `vic3-mod-manager` (`main`) | Python `vic3mm`: the most complete: order engine with explanations and fixes, persistent library, safe zip install, per-playset saves, compare, update check, CSP/Host/Origin hardening, property + fuzz tests, CI, docs |
| `My-Mod-Manager` | a one-line README |

## What was done
1. **Chose the base**: VIC3's engine, as the most complete and best tested (decision 3 in docs/06). CK3 and EU5 had no features VIC3 lacked except the ones listed next.
2. **Renamed and generalised** it to the `modmanager` package with a `Game` profile layer (`games.py`): paths, install detection, load file name/style, definition folders, theme, legacy config names.
3. **Ported in**: EU5's install detection (registry, vdf libraries, drive guesses, renamed installs), setup dialog, base-game comparison (made lazy), `INJECT:` as *patch*, `type`/`rel_type` relationships and metadata ids, enable/disable all/prune, share format (now game-aware, legacy formats accepted), rolling `.bak`; CK3's `dlc_load.json` export, per-script-folder definition keys, cycle report in manual mode too.
4. **Dropped on purpose**: CK3's bundled Paradox logo; EU5's automatic artwork fetch from Steam (network only on explicit actions now); the unapproved Tauri/Rust plan (kept as history in docs/06).
5. **New**: game switcher with per-game themes and per-game config, app-wide settings, migration from the standalone managers, presets, Workshop download helpers (Steam page, optional steamcmd), per-game stub-game launch tests, a multi-game browser test.
6. **Documentation**: README and docs/00-13 (this set).
7. **Tests**: 244 unit/API/fuzz/stub-game tests and four browser end-to-end scripts, all green locally on Python 3.11/3.12/3.13 (a static check confirms nothing needs newer than 3.8, which is not installed here).

## The RICE request
Asked for "the entire RICE stack" as custom profiles that are downloaded and launched on request. Findings: RICE is a CK3 mod ("Regional Immersion and Cultural Enrichment", Workshop id `2273832430`); its page names companions. The Workshop pages were readable only through an automated summariser that returned inconsistent data (mislabelled ids, claims the pages were removed), so **no id beyond RICE itself is confirmed**. What was built: a general presets mechanism and a draft `ck3-rice-stack` preset marked `unverified`. Downloading and launching cannot be done from this cloud sandbox (no Steam, no game); they run on the user's PC, only when a button is pressed (docs/11).

## Not done / not verified
- **Never run on a real CK3, EU5 or VIC3 install.** Load file name/format, whether the stock launcher overrides it, EU5's metadata layout and load style, `steam://` argument passing, the `launcher-settings.json` version key, the Steam logo-cache path, and save-link behaviour are from recollection or from the earlier managers' assumptions (docs/02, docs/13). The user offered to provide real file listings; they will replace guesses with facts.
- **CI has never run on GitHub** (matrix, the Windows `.exe`, the release job). Actions are pinned to major tags.
- Windows paths and junctions are untested (everything ran on Linux).
- steamcmd and the Steam page opener were tested with fakes only.
- The update checker was tested with a fake GitHub; the repository may be private or have no releases yet.
- The draft RICE preset's ids are unconfirmed.
- Not implemented: `.7z`/`.rar`, stock-launcher playset import, Paradox Mods/Nexus browsing, update notifications, MO2-style tags/separators/file-level tools (see docs/05 and the MO2 comparison in the chat).
- The three standalone repositories were not changed by this work.
