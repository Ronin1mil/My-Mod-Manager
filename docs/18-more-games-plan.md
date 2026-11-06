# Plan: more games (Imperator: Rome, Stellaris, Civilization VI, Cities: Skylines)

**Update (1.2.0):** Europa Universalis IV, Hearts of Iron IV, Stellaris and Imperator: Rome are now built in (`verified=False`), with their folders taken from Irony Mod Manager's code (docs/02). Section 1 below is done except the real-install check; Crusader Kings II is a template in **Add a game (beta)**. Every file name and path below is **from memory of other mod managers and must be checked on a real install** before a game is marked as working; each game ships with `verified = False` like Bannerlord did. The games used to prove the app are Crusader Kings III, Europa Universalis V, Victoria 3 and Bannerlord ([22-checked-on-a-real-pc.md](22-checked-on-a-real-pc.md) shows how they were checked).

## How to add one (also for a local session on a PC that has the game)
1. Install the game, run it once, enable two or three mods in its own launcher.
2. In the app: **Add a game (beta)** with the template, then **Settings -> Game -> Check this game**. It says what was found and what was looked for. Correct the field it points at until every check passes.
3. Press Play on a small playset, then send or read `RoninModManager-<game id>.log`: it holds the game's files before and after, and again 15 and 90 seconds later. If the game rewrites its own file, that is where it shows (this is how EU5's real format was found).
4. Move what you learned into `modmanager/games.py` as a built-in `Game` with `verified=False`, pin it in `tests/test_games.py`, add fake-install tests (copy the Bannerlord or EU5 ones), a section in `docs/02-game-notes.md`, and a CHANGELOG entry.
5. Run `python -m unittest discover -s tests -t .`, push to `nightly`, and use the nightly build. Only after a confirmed Play does the game become `verified=True`.

## Order of work
1. **Stellaris** and **Imperator: Rome** (Paradox engine, small changes)
2. **Civilization VI** (new kind: `.modinfo` mods, no load order)
3. **Cities: Skylines** (new kind: mods enabled inside the game's own settings, riskiest)

Each game is its own release (0.9.0, 0.10.0, ...), with a changelog section, docs page, fake-install tests and an e2e script, as for Bannerlord.

## 1. Stellaris and Imperator: Rome (kind `paradox`)
| | Stellaris | Imperator: Rome |
|---|---|---|
| Steam app id | 281990 | 859580 |
| User folder | `Documents/Paradox Interactive/Stellaris` | `Documents/Paradox Interactive/Imperator` |
| Load file | `dlc_load.json` (mods as `mod/ugc_<id>.mod`) | `dlc_load.json`, same shape |
| Launcher database | `launcher-v2.sqlite` | `launcher-v2.sqlite` |
| Install marker | `common` straight under the install folder | `game/common` |
| Script folders for conflicts | `common`, `events`, `map`, `localisation` | `common`, `events` |

Work needed:
- `Game` gets a field for where the base content lives (`content_dir`: `game` for most, empty for Stellaris). `vanilla_dir_name`, the base-game comparison and `detect` use it instead of the hard-coded `"game"`.
- The Stellaris launcher also keeps `game_data.json` / `mod_registry.json`; check whether the game needs them updated or only `dlc_load.json`.
- Presets: none yet; `tools/make_preset.py` can make them from Workshop collection links you send.
- Check on a real PC: user folder, load file name and format, descriptor names, version in the corner, launcher import.

## 2. Civilization VI (new kind `modinfo`)
- Steam app id 289070. User data: `Documents/My Games/Sid Meier's Civilization VI/`; local mods in `Mods/`, Workshop mods in `steamapps/workshop/content/289070/<id>/`.
- A mod is a folder with a `<name>.modinfo` XML file: `Mod id="<GUID>"`, `Properties/Name`, `Version`, `Dependencies`/`References`/`Blocks` (other mods by GUID), `AffectsSavedGames`, `CompatibleVersions`.
- **There is no user-chosen load order**; the game orders by dependencies. So a playset here is "which mods are enabled", Auto-sort only checks that dependencies are present and flags blocked/incompatible pairs.
- **Open question that decides the design:** where the game stores which mods are enabled (I believe a database file in the user folder written by the in-game Additional Content screen). If it is a plain file or SQLite we can write it (with a backup first); if the game rewrites it on exit we can only start the game after writing. Needs a look at a real install before any code.
- No conflicts tab (no shared script folders), no per-playset saves.

## 3. Cities: Skylines (new kind `workshop-ids`)
- Steam app id 255710. Workshop items: `steamapps/workshop/content/255710/<id>/`; local mods: `%LOCALAPPDATA%/Colossal Order/Cities_Skylines/Addons/Mods/`.
- Mods are DLLs; the game itself stores which are enabled inside its own settings file, so a manager cannot change this from outside unless that file's format is understood. **Riskiest game:** the first step is read-only (list mods, show updates from Workshop timestamps, warn about missing dependencies), and "apply playset" is only added if the settings format can be written safely.
- Cities: Skylines II (app 949230) uses Paradox Mods playsets and is a different project.

## Shared work
- A per-game "how mods are enabled" abstraction next to `kind`, so Civ VI and Skylines do not need `if game.id == ...` in the server.
- UI: hide Conflicts, Saves and Compare for kinds that do not have them (already done for `modules`), hide Auto-sort for games without order.
- Each new game adds fake-install tests and a Playwright script; presets and launcher import are optional per game.

## Not decided
- Which other games are wanted? Cheap fits for the existing engine: Hearts of Iron IV, Crusader Kings II, Europa Universalis IV (same Paradox family). Total War, Skyrim and Stardew need their own kind.
- Civilization VI and Cities: Skylines wait until a real install shows how they store enabled mods.
