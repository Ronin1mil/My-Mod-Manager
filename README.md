# Ronin Mod Manager

One mod manager for **Crusader Kings III**, **Europa Universalis V**, **Victoria 3** and **Mount & Blade II: Bannerlord** (and games you add yourself, beta). Pick a playset, see *why* two mods fight, press **Play**, and the game starts with exactly that playset's mods.

Python standard library only (3.8+), no exe: it runs a small local server and shows it in its own Edge/Chrome window.

> **Made with AI.** Written with the help of an AI coding assistant (Claude by Anthropic) at the direction of its maintainer. Tested against fake installs and on one real Windows PC (see Status). Keep backups of your saves.

## Install (Windows)
1. Install **Python 3.8 or newer** from python.org (keep "py launcher" ticked; check with `py --version`). You also need Edge or Chrome.
2. Download **`Mod-Manager-python.pyzw`** from the [Releases page](../../releases) and double-click it (or run `py Mod-Manager-python.pyzw` in PowerShell to see what it is doing).
3. The app window opens. Pick your game in the sidebar. The first time, a setup dialog finds the install (every Steam library, any drive) and asks you to confirm it.

Later versions: press **Check for updates** in the app. It downloads the new file, checks its SHA-256 against the release's `SHA256SUMS.txt`, replaces itself and restarts. Your playsets and settings are kept.

There is no exe because Smart App Control blocks unsigned programs, so releases carry only this file. (Test builds still include an unsigned exe and installer for PCs that allow them.)

**From source** (any OS, also for development): `git clone`, or **Code → Download ZIP** and unzip. Then `python -m modmanager`, or double-click `Start Ronin Mod Manager.bat` (Windows) / `.command` (macOS/Linux).

## Use it in six steps
1. **Pick the game** in the sidebar (each game has its own playsets, library, backups and colours).
2. **Make a playset**: *+ New*, or *Presets* for a ready-made list, or *Import* the playsets the game's own launcher already has.
3. **Add mods**: the *Library* tab lists every local and Workshop mod found; add the ones you want and set their order on the *Load order* tab (drag rows, tick to enable). Drop a `.zip` on the window to install a mod.
4. **Fix warnings**: the *Warnings* tab names each issue (missing dependency, wrong order, incompatible mod) with a one-click fix. **Auto-sort** keeps dependencies first and explains each position ("why is it here?").
5. **Look at conflicts**: the *Conflicts* tab shows which mod wins when two change the same file or definition. *Compare* puts two playsets side by side.
6. **Press Play.** The app writes what the game needs and starts it. The log of what it did is saved (see below).

Right-click a playset for Open, Rename, Duplicate, Favourite, Settings and Delete.

## Status: what is confirmed on a real PC
| Game | Play | Notes |
|---|---|---|
| Crusader Kings III | **confirmed** | starts `ck3.exe` directly with the playset's mods |
| Europa Universalis V | **confirmed** | puts the mods into the game's own active playset (`playsets.json`) |
| Victoria 3 | not yet | file format checked on a real PC; Play not yet tried |
| Bannerlord | not yet | modules and dependencies checked on a real PC; Play not yet tried |
| Games you add | beta | never marked verified |

Everything else is tested against fake installs and a stub game ([docs/08-testing.md](docs/08-testing.md)). What a real PC showed, and what was fixed because of it: [docs/22-checked-on-a-real-pc.md](docs/22-checked-on-a-real-pc.md). Five-minute checks for the rest: [docs/13-verification-checklist.md](docs/13-verification-checklist.md).

## If something goes wrong
Send the file, not a description. Everything is in `Documents\Ronin Mod Manager\` (open Documents from File Explorer; OneDrive may redirect it):

| File | Holds |
|---|---|
| `RoninModManager-<game>.log` (for example `-eu5.log`) | what the app did with that game: what it found, every Play (playset, mods in order, the game's files before and after, and again 15 and 90 seconds later) |
| `RoninModManager-errors.log` | crashes, failed requests, page errors |
| `RoninModManager-activity.log` | test builds only: timing of every step |

Your Windows user name is replaced by `<user>` in these files. Settings → Problems shows the exact paths (that is the Settings section, not the *Warnings* tab). Settings → Game → **Check this game** reports what was found and what was looked for.

## Features
- **Playsets**: unlimited, each with its own mods, order, notes, launch arguments and (optionally) its own save folder; duplicate, export/import to share.
- **Library**: local and Workshop mods, flagged new / updated / removed; **Rescan** redoes start-up's work while the app runs.
- **Auto-sort** from dependencies with a "why is it here?" per mod.
- **Problems with one-click fixes**: missing/disabled dependency, wrong order, loops, incompatible mods, duplicate names, wrong game version, missing files, damaged metadata.
- **Conflicts with the winner shown**: whole-file overrides, same definition in different files (`REPLACE:` marked intentional, `INJECT:` listed as patches), `replace_path`, duplicate localization keys; and what each mod changes in the base game.
- **Compare playsets** side by side (*Compare* tab).
- **Import the launcher's playsets** ([docs/16](docs/16-launcher-import.md)).
- **Presets** from Workshop collections ([docs/11](docs/11-presets-and-downloads.md)); **getting Workshop mods** via *Open in Steam* or optional `steamcmd` (no password is ever handled by the app).
- **Install `.zip`/`.tar*` mods** by drag and drop (checked for unsafe contents); uninstall and upgrades keep the old version in a backup folder.
- **Saves per playset**: a playset made now gets its own save folder, so the game's save list shows only that playset's saves.
- **Add your own game** (beta, Stellaris and Imperator: Rome templates included, unchecked): [docs/20](docs/20-v0.9-plan.md).
- **Updates** from this repository's Releases, and an optional test channel ([docs/19](docs/19-test-builds-and-releases.md)). Checks are manual unless you turn on "check when the manager starts".

## What differs per game
| | Crusader Kings III | Europa Universalis V | Victoria 3 | Bannerlord |
|---|---|---|---|---|
| Steam app id | 1158310 | 3450310 | 529340 | 261550 |
| What Play writes | `dlc_load.json` | `playsets.json` (active playset) and `dlc_load.json` | `content_load.json` | nothing |
| Entries | `mod/<name>.mod`, `mod/ugc_<id>.mod` | folder paths in the game's playset | `enabledMods: [{"path": <folder>}]` | module ids on the command line |
| Play starts | `binaries/ck3.exe` | Steam | `binaries/victoria3.exe` | `Bannerlord.exe` |
| Mod is | folder with `.mod`/metadata | folder with metadata | folder with metadata | folder with `SubModule.xml` |
| Conflict analysis | yes | yes | yes | no (load order only) |

More: [docs/02-game-notes.md](docs/02-game-notes.md), [docs/17-bannerlord.md](docs/17-bannerlord.md).

## Known limits
- The official launcher keeps its own playsets in `launcher-v2.sqlite`; this tool never edits it. Start the game from this tool so its load order is used.
- Mods install from `.zip` and `.tar*` archives; `.7z` and `.rar` are not supported.
- Definition scanning covers top-level keys in the game's script folders; it does not model per-database merge rules.
- Saves per playset are confirmed for CK3 only.
- Workshop ids in presets were checked on Steam but the presets were not played.
- Windows only for now; the Python code also runs on macOS and Linux, but nothing else is tried.

## Logo and trademarks
No game artwork is stored in this repository. The header shows each game's logo, read from your own Steam cache, a `logo.*` in the game's config folder, or a file passed with `--logo`. If none is found, the app downloads Steam's public logo once and keeps it on your PC (turn this off under Settings → App & updates, or with `MODMANAGER_FETCH_LOGOS=0`).

This is an unofficial fan tool, not affiliated with or endorsed by Paradox Interactive, Taleworlds or Valve. The games' names and logos belong to their owners.

## Command line
```bash
python -m modmanager                       # app window on 127.0.0.1:8765
python -m modmanager --browser             # default browser instead of the app window
python -m modmanager --no-browser          # only run the server
python -m modmanager --game eu5            # open this game first
python -m modmanager --game ck3 --user-dir "D:/Docs/Paradox Interactive/Crusader Kings III" --workshop-dir "D:/Steam/steamapps/workshop/content/1158310"
python -m modmanager --list-games | --version | --check-update
```
The server answers `127.0.0.1` only. Set `MODMANAGER_CONFIG_DIR` to keep the app's data somewhere else.

## Development
```bash
python -m unittest discover -s tests -t .          # ~500 unit/API/fuzz/stub-game tests, no game needed
npm i --no-save playwright && npx playwright install chromium
node tests/e2e/ui.mjs                               # browser end-to-end (one script per area in tests/e2e)
GAME=ck3 node tests/e2e/ui.mjs                      # the same flow on CK3
python tools/build_pyz.py dist/Mod-Manager-python.pyzw
```
Branches: work happens on `nightly`; every push builds the test build. `main` is releases only ([docs/15-releasing.md](docs/15-releasing.md), [docs/19-test-builds-and-releases.md](docs/19-test-builds-and-releases.md)). Add a game: [docs/03-architecture.md](docs/03-architecture.md).

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
| [docs/02-game-notes.md](docs/02-game-notes.md) | Per-game facts, what is confirmed |
| [docs/03-architecture.md](docs/03-architecture.md) | Modules, data, how to add a game |
| [docs/04-ui-design.md](docs/04-ui-design.md) | Screens and UX rules |
| [docs/05-roadmap.md](docs/05-roadmap.md) | Done and next |
| [docs/06-decisions.md](docs/06-decisions.md) | Decisions and why |
| [docs/07-security.md](docs/07-security.md) | Security rules |
| [docs/08-testing.md](docs/08-testing.md) | What is tested and how |
| [docs/09-build-log.md](docs/09-build-log.md) | History: how the three managers became one |
| [docs/10-migration.md](docs/10-migration.md) | Moving from the standalone managers |
| [docs/11-presets-and-downloads.md](docs/11-presets-and-downloads.md) | Presets, Workshop downloads, steamcmd |
| [docs/12-api.md](docs/12-api.md) | HTTP API reference |
| [docs/13-verification-checklist.md](docs/13-verification-checklist.md) | Checks to run on a real install |
| [docs/14-updates-and-errors.md](docs/14-updates-and-errors.md) | Self-update, logs, the app window |
| [docs/15-releasing.md](docs/15-releasing.md) | How to publish a release |
| [docs/16-launcher-import.md](docs/16-launcher-import.md) | Importing the launcher's playsets |
| [docs/17-bannerlord.md](docs/17-bannerlord.md) | Bannerlord: modules, order, launching |
| [docs/18-more-games-plan.md](docs/18-more-games-plan.md) | Plan for Stellaris, Imperator, Civ VI, Cities: Skylines |
| [docs/19-test-builds-and-releases.md](docs/19-test-builds-and-releases.md) | Test builds (nightly) and releases |
| [docs/20-v0.9-plan.md](docs/20-v0.9-plan.md) | Adding your own games (beta), what was left out |
| [docs/21-dev-data-locations.md](docs/21-dev-data-locations.md) | Where every file and log is (for testers) |
| [docs/22-checked-on-a-real-pc.md](docs/22-checked-on-a-real-pc.md) | What a real PC showed, and the fixes |

## License
[MIT](LICENSE) © 2026 Ronin1mil
