# Ronin Mod Manager

One mod manager for **Crusader Kings III**, **Europa Universalis V**, **Victoria 3** and **Mount & Blade II: Bannerlord**. Pick a playset, see *why* two mods fight, press **Play**, and the game starts with exactly that playset's mods. Python standard library only (3.8+), and its own app window.

This repository replaces the three standalone managers (`ck3-mod-manager`, `eu5-mod-manager`, `vic3-mod-manager`). Nothing is read from their folders any more; playsets from the games' own launchers can be imported, see [docs/10-migration.md](docs/10-migration.md).

> **Made with AI.** This project was written with the help of an AI coding assistant (Claude by Anthropic) at the direction of its maintainer. It is tested against fake installs only (see Status below), so use it with that in mind and keep backups of your saves.

```bash
python -m modmanager                       # opens the app window (served on 127.0.0.1:8765), pick the game in the sidebar
python -m modmanager --browser             # use the default browser instead of the app window
python -m modmanager --no-browser          # only run the server
python -m modmanager --game eu5            # open a specific game first
python -m modmanager --game ck3 --user-dir "D:/Docs/Paradox Interactive/Crusader Kings III" \
                                --workshop-dir "D:/Steam/steamapps/workshop/content/1158310"
python -m modmanager --list-games
```

The first time you open a game, a setup dialog finds the install (every Steam library, any drive, renamed folders) and asks you to confirm it. You can paste *any* path inside the install and it resolves to the root.

> **Status:** everything is tested against fake installs and a stub game (see [docs/08-testing.md](docs/08-testing.md)). **Nothing has been run against a real CK3, EU5 or VIC3 install yet**, so the hand-off to the game (load file name and format, whether the stock launcher overrides it) is unverified. The in-app setup dialog says so, and [docs/13-verification-checklist.md](docs/13-verification-checklist.md) lists the five-minute checks that settle it per game.

## Download the app (recommended once a release exists)
Open the repository's **Releases** page. On Windows download **`Mod-Manager-Setup.exe`** and run it: it installs for your user (no administrator rights), adds a Start-menu entry (and optionally a desktop shortcut) and an uninstaller. Prefer no installer? `Mod-Manager-windows.exe` runs on its own. macOS and Linux apps are not built yet (saved for later); use the Python route below. No Python needed on Windows. Start it and your browser opens the app. When a newer release is published a banner offers **Update now**: the app downloads the new version, checks it against the release's `SHA256SUMS.txt`, replaces itself and restarts. Your playsets and settings live in your user folder and are kept.
Unsigned apps trigger a warning the first time: Windows SmartScreen ("More info" → "Run anyway"), macOS ("System Settings → Privacy & Security → Open Anyway"). See `docs/14-updates-and-errors.md`.

If something goes wrong, the details are written to **`Documents/Ronin Mod Manager/RoninModManager-errors.log`** (the red banner in the app shows the exact path). Send that file when reporting a problem.

## Window
The app opens in its own window and closing the window quits it. On Windows and macOS that is a native window around the system web view (Windows needs the Edge WebView2 runtime, which Windows 11 and current Windows 10 already have). Without it the app falls back to an Edge/Chrome "app" window, then to your default browser (`--browser` forces the browser). Under the hood it is still a small server on `127.0.0.1` that only this PC can reach. The native window is built and probed in CI but has **not** been opened on a real Windows or macOS desktop yet.

## Quick start (no Git)
On GitHub press **Code → Download ZIP**, unzip it, and double-click `Start Ronin Mod Manager.bat` (Windows) or `Start Ronin Mod Manager.command` (macOS/Linux). You need Python 3.8+ installed.

## Features
- **Three games, one app.** A game switcher with a per-game theme; every game keeps its own playsets, library, backups and settings. Adding a game is a data entry in `modmanager/games.py`.
- **Playsets**: unlimited, each with its own mods, load order, notes, extra launch arguments and (optionally) its **own save folder**; duplicate, export/import to share (a file for the wrong game is refused with a clear message).
- **Library**: scans local and Steam Workshop mods on start, on **Refresh** and when you return to the window; flags mods that are **new / updated / removed**.
- **Auto-sort** from dependencies (by name or by metadata id), with a **"why is it here?"** explanation per mod; your manual order is respected wherever no rule applies.
- **Problems with one-click fixes**: missing or disabled dependency (enables it and what it needs), wrong order, dependency loops, incompatible mods, duplicate names, mods built for another game version, missing files, damaged metadata.
- **Conflicts with the winner shown**: whole-file overrides, same definition in different files (`REPLACE:` winners marked intentional, `INJECT:` listed separately as *patches*), `replace_path` wiping earlier mods, duplicate localization keys.
- **Base-game comparison**: what each mod overrides in the vanilla game (toggle in Settings; base files are only parsed where a mod defines the same keys, so it stays fast).
- **Import the launcher's playsets**: the sidebar **Import** menu (and an automatic import when a game opens) brings in the playsets that already exist in the game's own Paradox launcher; see [docs/16-launcher-import.md](docs/16-launcher-import.md).
- **Presets**: curated playsets as plain JSON (for example a RICE stack for CK3); one click turns one into a playset and lists what is not installed yet. See [docs/11-presets-and-downloads.md](docs/11-presets-and-downloads.md).
- **Getting Workshop mods**: *Open in Steam* (you press Subscribe) or, optionally, `steamcmd` with an account you already logged in. No password is ever handled by this app.
- **Install `.zip` mods** by drag and drop (checked for unsafe contents); **uninstall** and **upgrades** keep the old version in a backup folder.
- **Compare playsets** side by side, with one-click *Add*, *Match state*, *Match order*.
- **Updates** from this repository's Releases: the downloaded app offers an **Update now** button (checksum-verified); a copy run from source only reports that a newer version exists. Checks are manual, `--check-update`, or on start (**off by default**).
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

**Bannerlord** works differently (modules with a `SubModule.xml`, started with a module list on the command line, no load file, no conflict analysis) and is **unverified on a real install**: see [docs/17-bannerlord.md](docs/17-bannerlord.md).

## Logo and trademarks
No game artwork is stored in this repository. The header shows each game's logo, read from your own Steam cache, a `logo.*` in the game's config folder, or a file passed with `--logo`. If none is found, the app downloads Steam's public logo once and keeps it on your PC (turn this off under Settings → App & updates, or with `MODMANAGER_FETCH_LOGOS=0`).

This is an unofficial fan tool. It is not affiliated with or endorsed by Paradox Interactive or Valve. Crusader Kings, Europa Universalis, Victoria and Steam, and their names and logos, belong to their owners.

## Known limits
- The official launcher keeps its own playsets in `launcher-v2.sqlite`; this tool does not edit it. Start the game through this tool so its load order is used.
- Mods install from `.zip` and `.tar` archives (`.tar.gz`, `.tar.bz2`, `.tar.xz`); `.7z` and `.rar` are not supported.
- Definition scanning covers top-level keys in the game's script folders; it does not understand per-database merge rules.
- Per-playset saves are opt-in until verified on a real install.
- Presets ship with **unverified** Workshop ids; read [docs/11](docs/11-presets-and-downloads.md) before relying on one.

## Development
```bash
python -m unittest discover -s tests -t .          # unit/API/fuzz/stub-game tests
npm i --no-save playwright && npx playwright install chromium
for t in ui order compare games features culture switch; do node tests/e2e/$t.mjs; done   # browser end-to-end
GAME=ck3 node tests/e2e/ui.mjs                      # the same flow on CK3
```
Set `MODMANAGER_CONFIG_DIR` to keep the config somewhere else (tests do).

## Sources and credits
Where facts in this project come from. Nothing here is copied code; the open-source projects were read to learn file layouts.

**File formats and behaviour**
- Paradox launcher database (`launcher-v2.sqlite`: tables `playsets`, `playsets_mods`, `mods` and their columns): read from the source of [Irony Mod Manager](https://github.com/bcssov/IronyModManager), which already imports from it. See [docs/16-launcher-import.md](docs/16-launcher-import.md).
- Bannerlord modules (`SubModule.xml` elements, dependency and load-order rules, official module ids), the `_MODULES_*…*_MODULES_` launch argument, the executable path and the Workshop folder layout: read from the BUTR projects [Bannerlord.ModuleManager](https://github.com/BUTR/Bannerlord.ModuleManager) and [Bannerlord.LauncherManager](https://github.com/BUTR/Bannerlord.LauncherManager), and the [Bannerlord modding documentation](https://docs.bannerlordmodding.com/). See [docs/17-bannerlord.md](docs/17-bannerlord.md).
- Workshop collections and mod update times: [Steam Web API](https://steamcommunity.com/dev) (`ISteamRemoteStorage`), keyless public endpoints.
- Game logos: downloaded on your PC from Steam's public art server; the logos belong to their owners.
- Paradox game folder layouts, load files and mod descriptors (`dlc_load.json`, `content_load.json`, `.mod`, `metadata.json`): the games' own files and the author's earlier standalone CK3, EU5 and VIC3 managers, which this project replaces.

**Built-in presets** are lists of mods other people made and published on the Steam Workshop; the ids come from each collection's public page. The mods belong to their authors.
- Crusader Kings III: [A Game of Thrones The Definitive Collection (AGOT 0.4.40)](https://steamcommunity.com/sharedfiles/filedetails/?id=3631494889) (28 mods)
- Crusader Kings III: [RICE + Cultures Expanded (draft)](https://steamcommunity.com/sharedfiles/filedetails/?id=2829397295) (3 mods)
- Crusader Kings III: [Princes of Darkness (draft)](https://steamcommunity.com/sharedfiles/filedetails/?id=2216659254) (1 mod)
- Crusader Kings III: [RICE stack (draft)](https://steamcommunity.com/sharedfiles/filedetails/?id=2273832430) (4 mods)
- Crusader Kings III: [Seastar's AGOT Collection 1.19.0.6 Updated](https://steamcommunity.com/sharedfiles/filedetails/?id=3608639287) (93 mods)
- Crusader Kings III: [Small Maps](https://steamcommunity.com/sharedfiles/filedetails/?id=3814492113) (15 mods)
- Europa Universalis V: [Roman Empire Collection](https://steamcommunity.com/sharedfiles/filedetails/?id=3608056145) (27 mods)
- Victoria 3: [Community Flavor Playlist](https://steamcommunity.com/sharedfiles/filedetails/?id=3385177152) (44 mods)
- Victoria 3: [Ultra Historical Mod Series](https://steamcommunity.com/sharedfiles/filedetails/?id=2918558673) (9 mods)
- Victoria 3: [zw's Automated Vic3](https://steamcommunity.com/sharedfiles/filedetails/?id=3373559506) (7 mods)
- Victoria 3: [zw's Vic3 Mods](https://steamcommunity.com/sharedfiles/filedetails/?id=3373555715) (22 mods)

**Tools used to build and ship**: [PyInstaller](https://pyinstaller.org/) (single-file apps), [Inno Setup](https://jrsoftware.org/isinfo.php) (Windows installer), [pywebview](https://pywebview.flowrl.com/) (the native window on Windows and macOS), [Playwright](https://playwright.dev/) (browser tests), GitHub Actions.

This project was written with the help of an AI coding assistant (see the note at the top).

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
| [docs/16-launcher-import.md](docs/16-launcher-import.md) | Importing the launcher's playsets |
| [docs/17-bannerlord.md](docs/17-bannerlord.md) | Bannerlord: modules, order, launching |
| [docs/19-test-builds-and-releases.md](docs/19-test-builds-and-releases.md) | Test builds (nightly) and how releases are made |

## License
[MIT](LICENSE) © 2026 Ronin1mil
