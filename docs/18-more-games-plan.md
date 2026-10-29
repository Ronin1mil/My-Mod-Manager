# Plan: more games (Imperator: Rome, Stellaris, Civilization VI, Cities: Skylines)

Nothing here is built yet. Every file name and path below is **from memory of other mod managers and must be checked on a real install** before the game is marked as working; each game ships with `verified = False` like Bannerlord did. The games I know you play from this project are Crusader Kings III, Europa Universalis V, Victoria 3 and Bannerlord, so anything beyond the four you named is a question at the end.

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

## Questions for you
1. Which other games do you play that lack a good mod manager? Candidates that fit the existing engine cheaply: Hearts of Iron IV, Crusader Kings II, Europa Universalis IV (Paradox, same family as the three already here). Others (Total War, Skyrim, Stardew) need their own kind.
2. Should Civilization VI and Cities: Skylines wait until a real install shows how they store enabled mods?
