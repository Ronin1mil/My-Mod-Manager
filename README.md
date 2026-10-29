# My Mod Manager

One mod manager for Paradox grand strategy games: **Crusader Kings III**, **Europa Universalis V** and **Victoria 3**. Pick a playset, see *why* two mods fight, press **Play**, and the game starts with exactly that playset's mods. Python standard library only (3.8+), a local web UI, no account, no telemetry.

This repository replaces the three standalone managers (`ck3-mod-manager`, `eu5-mod-manager`, `vic3-mod-manager`). Their playsets are imported automatically on first start, see [docs/10-migration.md](docs/10-migration.md).

```bash
python -m modmanager                       # opens http://127.0.0.1:8765, pick the game in the sidebar
python -m modmanager --game eu5            # open a specific game first
python -m modmanager --game ck3 --user-dir "D:/Docs/Paradox Interactive/Crusader Kings III" \
                                --workshop-dir "D:/Steam/steamapps/workshop/content/1158310"
python -m modmanager --list-games
```

The first time you open a game, a setup dialog finds the install (every Steam library, any drive, renamed folders) and asks you to confirm it. You can paste *any* path inside the install and it resolves to the root.

> **Status:** everything is tested against fake installs and a stub game (see [docs/08-testing.md](docs/08-testing.md)). **Nothing has been run against a real CK3, EU5 or VIC3 install yet**, so the hand-off to the game (load file name and format, whether the stock launcher overrides it) is unverified. The in-app setup dialog says so, and [docs/13-verification-checklist.md](docs/13-verification-checklist.md) lists the five-minute checks that settle it per game.

## Download the app (recommended once a release exists)
Open the repository's **Releases** page. On Windows download **`Mod-Manager-Setup.exe`** and run it: it installs for your user (no administrator rights), adds a Start-menu entry (and optionally a desktop shortcut) and an uninstaller. Prefer no installer? `Mod-Manager-windows.exe` runs on its own. macOS and Linux: `Mod-Manager-macos` / `Mod-Manager-linux` (make executable, then run). No Python needed. Start it and your browser opens the app. When a newer release is published a banner offers **Update now**: the app downloads the new version, checks it against the release's `SHA256SUMS.txt`, replaces itself and restarts. Your playsets and settings live in your user folder and are kept.
Unsigned apps trigger a warning the first time: Windows SmartScreen ("More info" → "Run anyway"), macOS ("System Settings → Privacy & Security → Open Anyway"). See `docs/14-updates-and-errors.md`.

If something goes wrong, the details are written to **`Documents/ModManager-errors.log`** (the red banner in the app shows the exact path). Send that file when reporting a problem.

## Quick start (no Git)
On GitHub press **Code → Download ZIP**, unzip it, and double-click `Start Mod Manager.bat` (Windows) or `Start Mod Manager.command` (macOS/Linux). You need Python 3.8+ installed.

## Features
- **Three games, one app.** A game switcher with a per-game theme; every game keeps its own playsets, library, backups and settings. Adding a game is a data entry in `modmanager/games.py`.
- **Playsets**: unlimited, each with its own mods, load order, notes, extra launch arguments and (optionally) its **own save folder**; duplicate, export/import to share (a file for the wrong game is refused with a clear message).
- **Library**: scans local and Steam Workshop mods on start, on **Refresh** and when you return to the window; flags mods that are **new / updated / removed**.
- **Auto-sort** from dependencies (by name or by metadata id), with a **"why is it here?"** explanation per mod; your manual order is respected wherever no rule applies.
- **Problems with one-click fixes**: missing or disabled dependency (enables it and what it needs), wrong order, dependency loops, incompatible mods, duplicate names, mods built for another game version, missing files, damaged metadata.
- **Conflicts with the winner shown**: whole-file overrides, same definition in different files (`REPLACE:` winners marked intentional, `INJECT:` listed separately as *patches*), `replace_path` wiping earlier mods, duplicate localization keys.
- **Base-game comparison**: what each mod overrides in the vanilla game (toggle in Settings; base files are only parsed where a mod defines the same keys, so it stays fast).
- **Presets**: curated playsets as plain JSON (for example a RICE stack for CK3); one click turns one into a playset and lists what is not installed yet. See [docs/11-presets-and-downloads.md](docs/11-presets-and-downloads.md).
- **Getting Workshop mods**: *Open in Steam* (you press Subscribe) or, optionally, `steamcmd` with an account you already logged in. No password is ever handled by this app.
- **Install `.zip` mods** by drag and drop (checked for unsafe contents); **uninstall** and **upgrades** keep the old version in a backup folder.
- **Compare playsets** side by side, with one-click *Add*, *Match state*, *Match order*.
- **Update check** against this repository: manual, `--check-update`, or on start (**off by default**). It never downloads or installs anything.
- **Play** writes the game's load file (previous one saved as `.bak`), creates missing Workshop descriptors where the game needs them, and starts the game through Steam (or `--game-exe`).

## What differs per game
| | Crusader Kings III | Europa Universalis V | Victoria 3 |
|---|---|---|---|
| Steam app id | 1158310 | 3450310 | 529340 |
| Load file in the user folder | `dlc_load.json` | `dlc_load.json` | `content_load.json` |
| Entries in it | `mod/<name>.mod`, `mod/ugc_<id>.mod` | `mod/<folder>`, or the Workshop path | `mod/<name>.mod`, `mod/ugc_<id>.mod` |
| Install marker | `game/common` | `game/in_game` | `game/common` |
| Definition folders | `common/`, `events/` | `in_game/common/` | `common/`, `events/` |
| Base game compared | all of `game/` | `in_game`, `main_menu`, `loading_screen` | all of `game/` |

Details and what is still to verify: [docs/02-game-notes.md](docs/02-game-notes.md).

## Logo and trademarks
No game artwork is stored in this repository. The sidebar shows the game's logo only if it can read it from *your* Steam cache, a `logo.*` you put in the game's config folder, a file you pass with `--logo`, or one you download yourself with `--fetch-logo`; otherwise a text wordmark. (The standalone CK3 manager bundled a Paradox logo; that was dropped here.)

## Known limits
- The official launcher keeps its own playsets in `launcher-v2.sqlite`; this tool does not edit it. Start the game through this tool so its load order is used.
- `.zip` archives only (no `.7z`/`.rar` yet).
- Definition scanning covers top-level keys in the game's script folders; it does not understand per-database merge rules.
- Per-playset saves are opt-in until verified on a real install.
- Presets ship with **unverified** Workshop ids; read [docs/11](docs/11-presets-and-downloads.md) before relying on one.

## Development
```bash
python -m unittest discover -s tests -t .          # 244 unit/API/fuzz/stub-game tests
npm i --no-save playwright && npx playwright install chromium
for t in ui order compare games; do node tests/e2e/$t.mjs; done   # browser end-to-end
GAME=ck3 node tests/e2e/ui.mjs                      # the same flow on CK3
```
Set `MODMANAGER_CONFIG_DIR` to keep the config somewhere else (tests do).

## Docs
| File | Purpose |
|---|---|
| [docs/00-vision.md](docs/00-vision.md) | Vision, principles, non-goals |
| [docs/01-requirements.md](docs/01-requirements.md) | Feature checklist |
| [docs/02-game-notes.md](docs/02-game-notes.md) | Per-game facts, assumptions, what to verify |
| [docs/03-architecture.md](docs/03-architecture.md) | Modules, data, how to add a game |
| [docs/04-ui-design.md](docs/04-ui-design.md) | Screens and UX rules |
| [docs/05-roadmap.md](docs/05-roadmap.md) | Milestones |
| [docs/06-decisions.md](docs/06-decisions.md) | Decisions, including the merge |
| [docs/07-security.md](docs/07-security.md) | Security rules |
| [docs/08-testing.md](docs/08-testing.md) | What is tested and how |
| [docs/09-build-log.md](docs/09-build-log.md) | What was built, found, fixed and left unverified |
| [docs/10-migration.md](docs/10-migration.md) | Moving from the standalone managers |
| [docs/11-presets-and-downloads.md](docs/11-presets-and-downloads.md) | Presets, Workshop downloads |
| [docs/12-api.md](docs/12-api.md) | HTTP API reference |
| [docs/13-verification-checklist.md](docs/13-verification-checklist.md) | Checks to run on a real install |
