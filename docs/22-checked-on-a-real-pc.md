# Checked on a real PC

What the four built-in games actually look like on a Windows 11 PC with all of them installed from Steam (library on `G:\SteamLibrary`, Documents not redirected), read in October 2026, and what was changed because of it. Paths use `<user>` for the Windows user name. Nothing on that PC was changed by the checks: the launcher databases were read from copies.

## Summary
| Game | Version | Play | What changed |
|---|---|---|---|
| Crusader Kings III | 1.20.1.2 | **confirmed** (`verified=True`) | Play starts `binaries/ck3.exe` directly instead of going through Steam |
| Europa Universalis V | 1.4.5 | **confirmed** (`verified=True`) | Version read from the game's `debug.log` |
| Victoria 3 | 1.14.5 | **not yet confirmed** | Load file format fixed; Play starts `binaries/victoria3.exe` directly |
| Bannerlord | 1.5.6 | **not yet confirmed** | New playsets also start with `BirthAndDeath` and `NavalDLC` |

## Where things are
| | CK3 | EU5 | VIC3 | Bannerlord |
|---|---|---|---|---|
| User folder | `Documents\Paradox Interactive\Crusader Kings III` | `Documents\Paradox Interactive\Europa Universalis V` | `Documents\Paradox Interactive\Victoria 3` | `Documents\Mount and Blade II Bannerlord` (only `Game Saves`) |
| Load file | `dlc_load.json` | `dlc_load.json` + `playsets.json` | `content_load.json` | none (command line) |
| Workshop | `steamapps\workshop\content\1158310` | `...\3450310` | `...\529340` | `...\261550` |
| Launcher database | `launcher-v2.sqlite` | none (`playsets.json` is the list) | `launcher-v2.sqlite` | `Configs\LauncherData.xml` **not present** |
| `launcher\launcher-settings.json` | yes (`exePath ../binaries/ck3.exe`, `exeArgs -gdpr-compliant`) | **no `launcher` folder** | yes (`exePath ../binaries/victoria3.exe`) | n/a |

## Victoria 3: the load file was written in the wrong format
The app wrote `{"enabled_mods": ["mod/ugc_<id>.mod", ...]}` like CK3. The file the Paradox launcher writes is different:

```json
{"enabledMods": [{"path": "G:\\SteamLibrary\\steamapps\\workshop\\content\\529340\\3385002128"},
                 {"path": "C:\\Users\\<user>\\Documents\\Paradox Interactive\\Victoria 3\\mod\\cheat_menu_quiet"}],
 "disabledDLC": [], "enabledUGC": []}
```

Local mods are bare folders in `mod/` with a `.metadata/metadata.json`; there are no `.mod` files at all, and the launcher database leaves `gameRegistryId` empty for every mod. The app's own game log showed this as `content_load.json: ... ? mods enabled`. So the old format was never read by the game: Play in the app had no effect on Victoria 3.

Fix: a new `load_style="enabled_paths"`. The app writes `enabledMods` with each mod's absolute folder in Windows form, keeps `enabledUGC`, `disabledDLC` and any other key, writes no stubs and saves the old file as `content_load.json.bak`.

## CK3 and Victoria 3: the Paradox launcher replaced the load file
Play used to open `steam://run/<app id>`. For these two games Steam opens the Paradox launcher, and when you press Play there the launcher writes the load file from **its own** active playset. On the PC, `dlc_load.json` and `launcher-v2.sqlite` were rewritten in the same second (12:24:42 / 12:24:44), as were `content_load.json` and the launcher cache for Victoria 3, so whatever the app had written was replaced.

Fix: when the install has `launcher/launcher-settings.json` with an `exePath` (resolved inside the install only), Play starts that exe directly with its `exeArgs` (`-gdpr-compliant`) followed by the playset's launch arguments, the way the launcher itself starts the game. A `--game-exe` set by you still wins; a game without that file still goes through Steam. Settings > Problems and the game log say which way Play goes.

**CK3 confirmed:** Play on a 20-mod playset started `ck3.exe -gdpr-compliant` directly; the game mounted exactly those 20 mods, and `launcher-v2.sqlite` was not touched. **Victoria 3, to confirm:** press Play on a playset in the app. The game should start without the Paradox launcher window, and its main menu's mod list (or `logs/debug.log`) should show the playset's mods. Steam must be running.

## Europa Universalis V: confirmed
At 23:16:10 the app made "Initial playset" the active one in `playsets.json`. At 23:16:15 the game's `logs/debug.log` said `Switching to playset index 1, Name: Initial playset` and listed the same 17 mods, in order. Loading mods was also confirmed by playing.

EU5 has no `launcher` folder, so the version showed as "unknown". The game writes it into `logs/debug.log` (`... matched game version 1.4.5`), so that is now the fallback for any Paradox game without `launcher-settings.json`. It is only there after the game has started once with a mod.

## Bannerlord
- Version `v1.5.6` from `Modules/Native/SubModule.xml`: read correctly.
- Installed official modules and their dependencies (from each `SubModule.xml`): `Native`; `SandBoxCore` → Native; `BirthAndDeath`, `CustomBattle`, `SandBox` (id `Sandbox`) → Native, SandBoxCore; `StoryMode` → … Sandbox; `NavalDLC` → … StoryMode; `Multiplayer`. A new playset now starts with all installed ones except Multiplayer, in that order.
- `Configs/LauncherData.xml` does not exist, so Import has nothing to offer; that is expected, not an error.
- Play starts `bin/Win64_Shipping_Client/Bannerlord.exe` directly (the game log used to say "Steam" here, which was wrong; it now says "the game executable"). **To confirm:** make a playset, press Play, check the modules in game.

## Launcher import (CK3, Victoria 3)
The reader returned all 12 CK3 and 15 Victoria 3 playsets from copies of the real `launcher-v2.sqlite`. `dirPath` is stored with doubled backslashes; matching normalises it, so folders still match. One CK3 display name contains a non-UTF-8 byte and shows `?` in that spot.

## Tests on this PC
On a PC with the games installed, 12 tests in `test_detect.py` and `test_multigame.py` (Logos) fail before and after these changes: they expect "no game found" or "no logo" and find the real Steam install and Steam's logo cache. They are meant for a machine without the games, like CI.
