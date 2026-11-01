# Architecture

**Python 3.8+ standard library only**, a local HTTP server and a plain HTML/CSS/JS UI. No build step, nothing to install.

## Modules (`modmanager/`)
| Module | Job |
|---|---|
| `games.py` | the `Game` profiles (CK3, EU5, VIC3, Bannerlord): app id, folders, load file/style, definition folders, theme |
| `customgames.py` | turns the "Add a game (beta)" form into a `Game` |
| `paths.py` | config dirs (`MODMANAGER_CONFIG_DIR`), user dirs, Steam libraries (registry, vdf, drive guesses), Workshop dirs, game version, logos |
| `detect.py` | find/describe installs for a game (`install_marker`, `appmanifest` renames, pasted paths) |
| `descriptor.py` | parse `.mod` (Clausewitz subset) and `metadata.json` |
| `scan.py` | discover mods (Paradox folders and Bannerlord `SubModule.xml` modules); conflicts: file / definition / patch / replace / localization, base-game comparison |
| `library.py` | persistent library with new/updated/removed tracking |
| `order.py` | validate, stable topological sort, explanations, one-click fixes |
| `store.py` | playsets (validated, atomic JSON, rolling `.bak`), share/import, global settings, the load-file writer and EU5's `playsets.json` writer |
| `collections.py` | turn a Steam Workshop collection into a preset |
| `updates.py` | per-mod update tracking for Workshop mods |
| `selfupdate.py` | replace the running packaged app with a newer release (checksum-verified) |
| `launcherdb.py` | read-only import of the game launcher's playsets |
| `gamelog.py`, `errorlog.py`, `perflog.py` | the per-game log, the error log, the activity log (test builds) |
| `bootworker.py` | worker processes that work out conflicts at start-up |
| `window.py` | the app window (Edge/Chrome app mode, default browser fallback) |
| `presets.py` | curated playsets: validate, load (built-in + yours), apply, save |
| `workshop.py` | Steam page opener and optional `steamcmd` download jobs |
| `install.py` | safe `.zip` install, upgrade backups, uninstall |
| `saves.py` | per-playset save folder links |
| `launch.py` | argument validation; spawn exe or `steam://` URL |
| `compare.py` | compare two playsets |
| `update.py` | GitHub release check (explicit, off by default) |
| `server.py` | `GameApp` (one game), `Hub` (all games + app settings), JSON API, static UI, security headers |
| `static/` | `index.html`, `app.js`, `style.css` (one theme, colours set per game from `games.py`) |

## Data
`%APPDATA%\Ronin Mod Manager\` on Windows (`~/.config/...` elsewhere, or `MODMANAGER_CONFIG_DIR`); the full list is in [21-dev-data-locations.md](21-dev-data-locations.md):
```
settings.json            app-wide: update check, dismissed version, last game
ck3/ eu5/ vic3/ bannerlord/ cg-<name>/   one folder per game
  playsets.json (+ .bak)   playsets and per-game settings (folders, base-game toggle, steamcmd)
  library.json             every mod ever seen, with change tracking
  presets/*.json           your presets
  saves/<playset id>/      per-playset save folders (opt-in)
  backups/  staging/       uninstalled/upgraded mods; zip extraction scratch
  logo.*                   optional, yours
```
Playset: `{id, name, mods:[ids in load order], disabled:[ids], notes, launch_args, auto_sort, separate_saves, created}`. Mod id: `local:<name>` or `ws:<workshop id>`; ids are the same as in the standalone managers so imported playsets keep working.

## Request flow
`Hub` creates a `GameApp` per game on first use (so a game you never open costs nothing and triggers no detection). Requests are routed by `/api/<game>/...`; app-wide routes (`/api/games`, `/api/settings`, `/api/update-check`) have no game segment. One request at a time touches state (a lock); uploads, update checks and downloads run outside it.

## Adding a game
1. Add a `Game(...)` to `games.py` (app id, folder names, `install_marker`, `load_file`, `load_style`, `def_dirs`, theme) and put it in `GAMES`.
2. `tests/test_games.py` pins the registry: update it. Parametrised tests (`tests/test_multigame.py`, `test_detect.py`, `test_store_games.py`) pick the new game up through `ALL`.
3. Add a section to docs/02 and docs/13; add a built-in preset in `modmanager/presets/<game>-*.json` if wanted.
4. If its load file needs a new style, extend `store.mod_entry` and `Game.load_style` and add a test next to `LoadFiles`.
5. A game that works like the existing ones does not need code at all: use **Add a game (beta)** in the app ([20-v0.9-plan.md](20-v0.9-plan.md)), then move what you learn into `games.py`.
6. After a real Play, read `RoninModManager-<game>.log`: it shows what the game's files looked like before and after.

## Why Python and not a Tauri/Rust rewrite
The earlier CK3 plan proposed Tauri + Rust. That plan was never approved, and the Python app already works, is easy to audit and installs with nothing. The core is separate from the UI behind a JSON API, so a native shell stays possible. (See docs/06.)
