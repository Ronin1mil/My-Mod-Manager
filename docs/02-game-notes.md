# Game notes

Legend: **[known]** documented or confirmed by the working standalone managers' behaviour on the files they read; **[assumed]** best knowledge, not confirmed on a real install; **[verify]** a specific check in [13-verification-checklist.md](13-verification-checklist.md). The values below are exactly what `modmanager/games.py` encodes and `tests/test_games.py` pins. **CK3 and EU5 are marked `verified`** (Play confirmed on a real install). What was read from a real PC for every game is in [22-checked-on-a-real-pc.md](22-checked-on-a-real-pc.md).

## Shared (all three games)
- User dir: `Documents/Paradox Interactive/<Game>` (Windows, OneDrive-redirected Documents is handled), `~/.local/share/Paradox Interactive/<Game>` (Linux), `~/Library/Application Support/Paradox Interactive/<Game>` (macOS). **[known]**
- Local mods: `<user dir>/mod/<name>/` plus an optional `<user dir>/mod/<name>.mod` stub with `path="mod/<name>"`. A bare folder with its own metadata also counts. **[known]**
- Workshop mods: `<steam library>/steamapps/workshop/content/<app id>/<id>/`. Every library in `libraryfolders.vdf`, the Windows registry and common hand-made libraries (`G:\SteamLibrary`) are searched. A `ugc_<id>.mod` stub in `mod/` for a Workshop mod we already found is ignored. **[known]**
- Mod metadata, first hit wins: `.metadata/metadata.json`, `metadata/metadata.json`, `metadata.json`; falling back to `descriptor.mod` (Clausewitz `key="value"`, `key={ "a" "b" }`, `#` comments, `#` inside quotes is text). Metadata fields: `name`, `id`, `version`, `supported_game_version`, `tags`, `short_description`, `relationships[]` (`rel_type` or `type`: `dependency`, `incompatible`; `display_name`/`name`, `id`), `game_custom_data.{replace_paths,multiplayer_synchronized}`. **[assumed]** for EU5; **[known]** shape for CK3/VIC3 descriptors. Wrong-typed fields are ignored, damaged JSON becomes a warning on the mod.
- Dependencies are matched by metadata id first, then by **name**, a Workshop id or `ugc_<id>`. Names are not unique; duplicates are reported.
- Game version: `<install>/launcher/launcher-settings.json` (`rawVersion`, else `version`, first `1.2.3`-style number); a game without that file (EU5) uses the last `game version 1.2.3` in `<user dir>/logs/debug.log`. Unknown version = no version warnings. **[known]** on a real CK3, VIC3 and EU5
- Play: when `launcher/launcher-settings.json` names an `exePath` (CK3, VIC3), that exe is started directly with its `exeArgs` and the playset's arguments. Going through Steam opens the Paradox launcher, which writes its own playset over the load file when you press Play there. Games without that file (EU5) still start through Steam. **[known]** for CK3, **[verify]** for VIC3
- Load order: later mods override earlier ones. Same relative path: the whole file is replaced. **[known]**
- Definitions: top-level `key = {` in the game's script folders is a definition. Two mods defining the same key **in the same script folder** (`common/traits`) but different files both load; the later wins (*definition* conflict). The same key in *different* folders is not a clash. `REPLACE:`/`TRY_REPLACE:`/`REPLACE_OR_CREATE:` are intentional overrides (info); `INJECT:`/`TRY_INJECT:`/`INJECT_OR_CREATE:` merge into the target and are listed as *patches*. **[known]** for the prefixes; per-folder merge rules beyond this are not modelled.
- `replace_path` drops everything under that folder from *earlier* mods (and the base game). **[known]**
- Localization: same `(language, key)` in different files of different mods is reported (info); `localization/replace/` is skipped; never reported against the base game.
- Saves: `<user dir>/save games`; per-playset saves replace it with a link (an NTFS junction on Windows) while the game's own folder waits next to it as `save games (shared)`. **[verify]** that the game follows the link. Steam Cloud does not sync the save folders of CK3, VIC3 or EU5 (no `remotecache.vdf` on the PC checked).

## Crusader Kings III (`ck3`)
| | |
|---|---|
| Steam app id | 1158310 |
| Install marker | `game/common` |
| Definition folders | `common/`, `events/` |
| Load file | `<user dir>/dlc_load.json` = `{"enabled_mods": ["mod/Local.mod", "mod/ugc_123.mod"], "disabled_dlcs": []}` **[known]** by the previous standalone manager, **[verify]** it is honoured by the current game version and not overwritten by the launcher |
| Workshop entries | need `mod/ugc_<id>.mod` (created if missing) |
| Base game | the whole `game/` folder |

## Europa Universalis V (`eu5`)
| | |
|---|---|
| Steam app id | 3450310 |
| Install marker | `game/in_game` |
| Definition folders | `common/` anywhere in the first two path levels (`in_game/common/...`); events are not scanned |
| Active playset | **[known]** `<user dir>/playsets.json` (`{"playsets":[{name,isActive,orderedListMods:[{path,isEnabled}],DLC}]}`): the game starts with the playset marked `isActive`. Play writes the mods into the playset there with the same name as the app's playset (adds one if missing) and makes it the only one with `isActive` (backup `playsets.json.bak`). Confirmed: the game's `debug.log` says `Switching to playset ... Name: <that playset>` and loads its mods |
| Load file | `<user dir>/dlc_load.json` with `"enabled_mods": ["mod/<folder>", "<workshop path>"]` (folder for local, absolute Workshop folder for Workshop) **[assumed]**; the previous standalone manager could not confirm EU5 reads load order from this file **[verify]** |
| Base game | `in_game`, `main_menu`, `loading_screen` under `game/` |
| Metadata | `metadata.json` in `.metadata/` or `metadata/` **[assumed]** |

If the game ignores the file, use this tool for analysis, presets and sharing, and mirror the order in the stock launcher until the load file format is confirmed. The export is isolated in `store.write_load_file` / `store.mod_entry` and driven by `Game.load_style`.

## Victoria 3 (`vic3`)
| | |
|---|---|
| Steam app id | 529340 |
| Install marker | `game/common` |
| Definition folders | `common/`, `events/` |
| Load file | `<user dir>/content_load.json` = `{"enabledMods": [{"path": "G:\\SteamLibrary\\steamapps\\workshop\\content\\529340\\123"}, {"path": "C:\\Users\\<user>\\Documents\\Paradox Interactive\\Victoria 3\\mod\\Local"}], "enabledUGC": [], "disabledDLC": []}` **[known]**: written this way by the launcher on a real install (`load_style="enabled_paths"`) |
| Workshop entries | the Workshop folder itself; no `.mod` stubs (the real `mod/` folder has none, and the launcher database leaves `gameRegistryId` empty) |
| Extras | `multiplayer_synchronized` from `game_custom_data` shows an "MP-unsafe" badge |
| Launch arguments | passed to `binaries/victoria3.exe` after `-gdpr-compliant` |

## Changing what is assumed
Everything above is data (`games.py`) or one function (`store.mod_entry`). When a real-install check disagrees, fix the data, update the pinned values in `tests/test_games.py` / `tests/test_store_games.py`, set `verified=True` for that game, and update this page.

## Saves and versions (unverified)
- A new playset gets its own save folder (`<config>/<game>/saves/<playset id>`); playsets made before 0.9.12 keep what they had. One playset (or several) can play with the game's own `save games` folder: **Playset settings → Keep the game's saves with this playset only** makes that playset the one, and gives every other playset its own folder. *No mods* always uses the game's own folder.
- Switching: Play for a playset with its own saves renames the game's real folder to `save games (shared)` and links `save games` to the playset's folder; Play for a playset without its own saves removes the link and renames `save games (shared)` back. Nothing is copied or deleted; an interrupted switch is repaired on the next shared start.
- Before 0.9.12 switching back never happened on Windows: the link target came back as `\\?\C:\...` and never matched the app's folder, so once one playset with its own saves had been played, every later playset used that playset's folder.
- Save-version guard: compares major.minor of the installed game (`launcher/launcher-settings.json`) with the version the saves were made on. Source 1: a `version="x.y.z"` in the newest save's first 16 KB (works only if the header is readable text; **not confirmed for any game**). Source 2: the version recorded when this app last launched with that save folder (dependable). Patch releases are ignored. A wrong header guess only costs one "Launch anyway" click; switch it off in Settings.
