# Developer notes: where the data is (test builds)

For whoever is testing a nightly / test build. Not for end users. Everything below is on the Windows PC running the app; `%USERPROFILE%\Documents` may be redirected (OneDrive), so open it from File Explorer's "Documents" rather than typing the path.

## Send these when something goes wrong
| What | Where | Why |
|---|---|---|
| Error log | `Documents\Ronin Mod Manager\RoninModManager-errors.log` | every crash, failed request and page error |
| Activity log (test builds only) | `Documents\Ronin Mod Manager\RoninModManager-activity.log` (and `.log.1`, the older half) | timestamps and durations of every request, scan and update step; shows what was slow or stuck |
| "Check this game" report | Settings -> Game -> Check now -> Copy report | what was found and what was looked for (install, folders, mods, launcher) |
| Version | bottom left of the window, e.g. `v0.8.5 · test 5097204` | which build produced the logs |

The activity log is on automatically for test builds. For a normal release start the app with the environment variable `MODMANAGER_ACTIVITY_LOG=1`. Format: `date time.ms [thread] > label` when a step starts, `< label N ms` when it ends.

## The app's own data
Folder: `%APPDATA%\Ronin Mod Manager\` (that is `C:\Users\<you>\AppData\Roaming\Ronin Mod Manager\`)

| Path | Contents |
|---|---|
| `settings.json` | app-wide settings |
| `custom_games.json` | games added with "Add a game (beta)" |
| `parse-cache.json.gz` | what was read from mod files (definition names), so a restart does not read them all again; safe to delete |
| `<game>\playsets.json` | playsets and per-game settings (folders, colour scheme, text size, favourites) |
| `<game>\library.json` | the mod library: tags, sources, what is new or updated |
| `<game>\backups\` | mods moved aside when uninstalled or upgraded |
| `<game>\presets\`, `<game>\logo.*` | your own presets, downloaded logo |
| `window\` | the app window's own browser profile |

`<game>` is `ck3`, `eu5`, `vic3`, `bannerlord`, or `cg-<name>` for an added game. "Settings -> Erase all data" empties this whole folder (except `window`) after typing ERASE.

## The games' own files (read by the app; only the load file is written)
| Game | Documents folder | Load file written by Play | Launcher data read for Import |
|---|---|---|---|
| Crusader Kings III | `Documents\Paradox Interactive\Crusader Kings III\` | `dlc_load.json` | `launcher-v2.sqlite` |
| Victoria 3 | `Documents\Paradox Interactive\Victoria 3\` | `content_load.json` (`enabledMods`, absolute paths) | `launcher-v2.sqlite` |
| Europa Universalis V | `Documents\Paradox Interactive\Europa Universalis V\` | `dlc_load.json` (and the active playset in `playsets.json`, which is what EU5 really uses) | `playsets.json` |
| Mount & Blade II: Bannerlord | `Documents\Mount and Blade II Bannerlord\` | none (modules go on the command line) | `Configs\LauncherData.xml` |

Local mods: `<Documents folder>\mod\<mod>\` with a `mod\<mod>.mod` stub (Paradox games); Bannerlord modules: `<install>\Modules\<ModuleId>\`.

## Steam
| What | Where |
|---|---|
| Installs | `<Steam library>\steamapps\common\<game>\` |
| Workshop mods | `<Steam library>\steamapps\workshop\content\<app id>\<workshop id>\` |
| App ids | CK3 `1158310`, EU5 `3450310`, VIC3 `529340`, Bannerlord `261550` |

## Test build download
Release page of the rolling test build: https://github.com/Ronin1mil/My-Mod-Manager/releases/tag/test-build

Direct files (always the newest test build):
- https://github.com/Ronin1mil/My-Mod-Manager/releases/download/test-build/Mod-Manager-windows.exe
- https://github.com/Ronin1mil/My-Mod-Manager/releases/download/test-build/Mod-Manager-Setup.exe

Inside the app: Settings -> App & updates -> Test builds -> "Check for a test build".

## Start-up pass
Before the window opens, `serve()` runs `boot()` (server.py): for each game that was used (the last one, the one asked for with `--game`, and any with a folder in the app data folder) it reads the mod folders, loads `parse-cache.json.gz`, and works out the conflicts of every playset, printing each step to the terminal when there is one. The comparing runs in up to 6 worker processes (`modmanager/bootworker.py`: started as `python -I -c ...` with the package folder or the .pyzw on `sys.path`, a pickled job on stdin, the pickled answer on stdout, progress on stderr); they only read, and the app keeps their answers as if it had worked them out itself. `MODMANAGER_BOOT_PROCS=0` checks everything in the app's own process instead. `MODMANAGER_BOOT=0` skips it, `MODMANAGER_PREWARM=0` also stops the background work after it. The same lines go to the activity log (prefix `boot:`) on test builds.

`Documents\Ronin Mod Manager\RoninModManager-<game id>.log` (one per game, always on, ~1 MB, one `.1` copy): what the app found when the game opened, every Play (playset, mods in order, the game's files before/after writing, and again after 15 s and 90 s), failures. The Windows user name is replaced by `<user>`. `MODMANAGER_FOLLOW_UP=0` turns the 15/90 s look-again off (tests).
