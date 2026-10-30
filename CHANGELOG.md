# Changelog

## 0.9.2 - Saves per playset, CK3 and EU5 confirmed, Victoria 3 load file fixed, Bannerlord presets
Each playset now has its own saves, Play starts Crusader Kings III and Europa Universalis V with your playset's mods (both confirmed on a real PC), Victoria 3 gets the load file format it actually reads, and Bannerlord has eight ready-made presets.

**How to install (Python edition only, no exe)**
- You need Windows 10 or 11, **Python 3.8 or newer** from python.org and Edge or Chrome. Nothing else
- Download **`Mod-Manager-python.pyzw`** below and double-click it, or run `py Mod-Manager-python.pyzw`. Your playsets and settings are kept
- Already on 0.9.x? Use **Check for updates** in the app: it updates itself

**Not confirmed yet:** saves per playset, and Play for Victoria 3 and Bannerlord, have not been tried in the game since these fixes. If one does not start the way you expect, send `Documents\Ronin Mod Manager\RoninModManager-<game>.log`.

**What changed**

- **Every playset has its own saves.** A playset made from now on gets its own save folder, so the game's save list only shows that playset's saves (Prince of Darkness no longer lists your vanilla campaigns). One playset per game keeps the saves you already have: choose it in Playset settings with **Keep the game's saves with this playset only**, which also gives every other playset its own folder. Nothing is copied or deleted: while another playset plays, your existing `save games` folder waits next to it as `save games (shared)` and comes back when that playset (or *No mods*) starts. Not yet confirmed in a game
- **Fixed: going back to the game's saves never happened on Windows.** Once one playset with its own save folder had been played, every later playset used that folder too, and the first switch moved your saves to `save games (original backup)` and showed an empty folder afterwards
- **Victoria 3: Play now writes the load file the game reads.** The app wrote `content_load.json` like CK3's file (`"enabled_mods": ["mod/ugc_<id>.mod"]`), but Victoria 3 reads `"enabledMods": [{"path": "<mod folder>"}]` with full folder paths and uses no `.mod` files, so Play in the app did not change which mods the game loaded. It now writes the game's own format, keeps the other settings in the file and no longer creates `ugc_<id>.mod` files in Victoria 3's `mod` folder. Found by reading the files on a real install ([docs/22](docs/22-checked-on-a-real-pc.md))
- **CK3 and Victoria 3: Play starts the game itself, not the Paradox launcher.** Going through Steam opened the Paradox launcher, which writes its own playset over the app's load file when you press Play there. Play now starts the exe the launcher would start (`binaries/ck3.exe`, `binaries/victoria3.exe`, read from the game's `launcher/launcher-settings.json`) with the same `-gdpr-compliant` argument plus your playset's launch arguments. Steam must be running. A game executable you set yourself still wins; EU5 (no launcher folder) still starts through Steam. The game is started with `SteamAppId` set, the way Steam starts it: without it Victoria 3 asked Steam to start it again and quit, which opened the Paradox launcher anyway. Confirmed for CK3 (marked as verified); not yet confirmed for Victoria 3
- **Europa Universalis V is confirmed working** (marked as verified): Play makes your playset the game's active one and the game loads its mods in order. Its version, shown as "unknown" before (EU5 has no launcher folder), is now read from the game's own `logs/debug.log`
- **Bannerlord:** a new playset also starts with the official `BirthAndDeath` and `NavalDLC` modules when they are installed, in the order their dependencies need. The game log no longer says Play goes through Steam (it starts `Bannerlord.exe`)
- **Eight Bannerlord presets** from public Steam Workshop collections (Presets tab): 2026 Essentials, Immersive Vanilla, Mods That Every Bannerlord Player Should Have, Bannerlord 2026, Mods Of Bannerlord (War Sails), Realism Collection, Bannerlord v1.4.8 Modpack and BannerGourd, 12 to 50 mods each. Every id was checked on Steam; none was played, and most mods name 1.3/1.4 as their game version. A playset made from a Bannerlord preset now starts with the official modules (before, it had only the Workshop mods and the game could not start with it)
- The test suite can no longer open real links. On a PC with Steam, tests that pressed Play on a fake Victoria 3 sent the real `steam://run/529340`, so every test run opened the real Paradox launcher (which then wrote its own playset into the game's load file)
- Settings and the Presets tab link to Valve's SteamCMD page, for anyone who wants the optional steamcmd downloads
- Right-click a playset in the list for Open, Rename, Duplicate, Favourite, Settings and Delete (asks first; mods and its own saves are not touched). The built-in "No mods" playset has no menu
- **Rescan** also looks for steamcmd when Settings has none (or the file it named is gone): in PATH, `C:\steamcmd` and a `steamcmd` folder on each drive, Program Files, AppData, Downloads, Desktop and Documents. It fills in the path, and the account name when steamcmd has exactly one cached login. It only looks; steamcmd is never run by the search
- A steamcmd download without a saved login ("Cached credentials not found") now stops after the first item and says how to log in once (`steamcmd +login <account> +quit` in a terminal), instead of failing every item with steamcmd's last line
- **Open in Steam** goes through the missing mods one at a time: it opens the first mod's Steam page, then **Next mod** opens the one after it (with **Open it again** and **Stop**), instead of opening every page at once
- Custom games (beta) can use the new `enabled_paths` load style
- **Europa Universalis V now starts with the playset you launch.** EU5 starts with the active playset of its own list (`playsets.json` in its user folder) and ignores the load file this app wrote, so the game kept starting with whatever playset it already had. Play now puts the mods into the game's playset with the same name as yours (a new one when the game has none), makes it the active one, and writes the flags the way the game does. Your other playsets in that file and the DLC choice are kept; the old file is saved as `playsets.json.bak`. Not yet confirmed on a real EU5 install: the new game log (next point) shows what happened if it still fails
- **A log per game.** `Documents\Ronin Mod Manager\RoninModManager-<game>.log` (for example `RoninModManager-eu5.log`) records what the app found when the game opened (folders, mod counts, the game's own playset file), then for every Play the playset and its mods in order, what the game's files said before and after the app wrote them, and what they say again 15 and 90 seconds later (this shows whether the game or its launcher put its own playset back), with the playset file itself and the files that changed in the game's user folder, so a file that decides which playset starts shows up. Always on, about 1 MB at most, your Windows user name is replaced by `<user>`. Settings > Problems shows the path; send that one file when a game does not start the way the app said
- **Faster scanning.** Definitions are found by looking only at braces, strings and comments (about twice as fast as reading every word, same results), file lists and file reads run on several threads when the disk is slow (a disk with antivirus, a network drive; a fast disk stays single-threaded because threads would only slow it), and mod folders are read the same way. The terminal now shows what it is doing: `listing files`, `reading files 4000 of 16000`, `comparing 800 mods`. On the test machine a cold scan of 800 mods and 16,000 files went from 11 s to 7 s on a fast disk; a slow disk gains more
- **One window after an update.** The Python edition runs in an Edge/Chrome app window that stays open when the old copy exits, so an update used to show two windows. Now the old window waits until the new copy has finished its start-up work, then closes itself (or, when it cannot, says it can be closed), and the new copy opens its own. The window the new copy opens belongs to a browser that was already running, so the app now ends by itself about 2.5 minutes after the last page is closed (pages say they are open every few seconds). The first update FROM a version older than this one cannot close its old window, so the new copy continues in that window instead of opening another
- **Start-up does the slow work first.** Before the window opens, the app reads the mod folders of the games you use, loads what it saved last time, and works out the conflicts of every playset, then opens the real interface with everything ready. Progress is printed in the terminal (run `py Mod-Manager-python.pyzw` from PowerShell to watch it; a double-click has no terminal, so the window simply appears once it is ready). The files it has read are saved between starts, but the conflicts are worked out again every time. That work is now shared out over a few worker processes (up to 6, by playset size) so it runs on several cores at once: on an 8-core PC with 33 playsets in three games, start-up went from about 40 s to 16 s, with the same answers. If a worker cannot start (the frozen exe) or fails, that game is checked the old way; `MODMANAGER_BOOT_PROCS=0` turns the workers off. Set `MODMANAGER_BOOT=0` to skip this pass
- The game logo shows at once: it is served straight from the file on your PC (it no longer waits for the game's mods to be read first) and the browser keeps it. No shield is drawn behind it any more, and a game with no logo shows nothing there. The Steam logo download is skipped for games with no Steam app id
- A copy running a test build follows the test builds first: the update notice and "Check for updates now" offer a newer test build (the banner says "Test build abc1234 is available"), and no longer offer the release of the version it is already on. A release with a higher version number is still offered. Settings > App & updates > Test builds has a new **Go back to the release** button for leaving the test channel

## 0.9.1 - Fast switching between big playsets
Clicking between playsets with many mods is now instant after the first time, and the window no longer seems to ignore clicks.

**How to install (Python edition only, no exe)**
- You need Windows 10 or 11, **Python 3.8 or newer** from python.org (keep "py launcher" ticked; check with `py --version` in PowerShell) and Edge or Chrome. Nothing else
- Download **`Mod-Manager-python.pyzw`** below and double-click it, or run `py Mod-Manager-python.pyzw`. Your playsets and settings are kept
- Already on 0.9.0? Use **Check for updates** in the app: it updates itself

**What changed**

- Clicking a playset shows it at once. Before, every click read every file of every mod again, and slow scans from earlier clicks piled up behind each other until the window seemed to ignore clicks
- The file/definition conflicts of each playset are kept: going back to a playset you already opened is instant
- A click stops an older scan nobody is waiting for. After start-up the app works out the other playsets quietly in the background; the first start with a big mod list is the slow one, and what it read is saved in `parse-cache.json.gz` in the app folder, so later starts only look for changes
- Coming back to the window no longer rescans everything: if no mod was added, changed or removed, nothing is redrawn or recomputed. The **Rescan** button still re-reads everything, including files edited inside a mod
- The mod folders are read without holding up other clicks
- Updater: an old copy that cannot be removed no longer blocks the next update (it uses `.old1`, `.old2`, ... instead)
- Installer: uninstalling also removes those leftovers
- "Built" dates of test builds and releases are shown in your own time zone with the exact time, down to the second (they showed the UTC date, which can be a day ahead)

## 0.9.0 - Python edition (no exe), add your own games (beta)
**How to install (this release is the Python edition only)**

What you need:
- **Windows 10 or 11**
- **Python 3.8 or newer** from python.org. Keep "py launcher" ticked in its installer (it is by default). To check what you have, open PowerShell and run `py --version`: if it prints `Python 3.8` or higher you are done; if it says "not recognized", install Python first
- **Edge or Chrome** (for the app window; both are normally already there). Nothing else: no pip packages, no exe

Steps:
1. Download **`Mod-Manager-python.pyzw`** from this release and put it anywhere you like (for example a folder in Documents)
2. Double-click it. If nothing happens or Windows asks what to open it with, run it from PowerShell instead: `py Mod-Manager-python.pyzw`
3. Updates: a banner offers **Update now**; the app downloads the new file, checks it against `SHA256SUMS.txt`, tests that Windows lets it start, and only then replaces itself. Your playsets and settings (`%APPDATA%\Ronin Mod Manager`) carry over from any earlier version

Why this edition exists: Windows Smart App Control blocks every program that is not signed, including this app's exe and installer, and the files cannot be signed yet. This edition has no exe of ours: Windows' own signed Python runs it. There is no installer and no exe in this release; copies of the exe cannot update themselves to it, so download the file by hand once. The first start unpacks about 1 MB into `%LOCALAPPDATA%\Ronin Mod Manager\pyz`. The app window opens through Edge/Chrome (the native window library of the exe is not part of this edition); if neither is found it opens in your browser.

What is new
- **Python edition.** One file, `Mod-Manager-python.pyzw`, started by the Python launcher. It updates itself like the exe does
- **Add a game (beta).** The game list ends with "＋ Add a game (beta)…". A form (with Stellaris and Imperator: Rome as unverified starting points, or a blank Paradox-style or Bannerlord-style game) defines a game from data: its Steam id, its folders in Documents and Steam, the file that lists mods, the folders to check for conflicts, an accent colour. The game then works like a built-in one (playsets, load order, conflicts, launcher import, Play). Edit or remove it under Settings -> Game. Every name is checked so a field can never point outside its folder, and the game's own files are never changed by the form
- **Check this game (beta)** in Settings -> Game, for every game: lists what the app found (install, base content, version, user folder, load file, Workshop folder, mods, launcher playsets, how Play starts the game) and what it was looking for where something is missing, with a button to copy the report
- **Bigger Settings window** (and the Add a game form): as wide as the page minus the playset list's width on each side, so the playset list stays visible on the left with the same space mirrored on the right
- **Safer self-update.** The downloaded file is started once (`--version`) before it replaces anything. If Windows refuses it (Smart App Control "Application Control policy has blocked this file", error 4551, or antivirus), nothing is changed and the page says why, instead of hanging at "Restarting..." with the blocked file already in place. If the new copy cannot start or ends at once after the swap, the previous version is put back
- A test build now says so plainly: an orange "TEST BUILD <id>" under the version, "(test build)" in the window title and in Settings

## 0.8.5 - checkboxes that always click, faster scan, activity log
- **Fix: the enable/disable checkbox sometimes ignored a click** (seen on 1440p screens). The box was tiny and sat inside a draggable row, so a slightly moving mouse started a drag instead of a click, and a list redraw (a late warning check, or the window regaining focus) between mouse-down and mouse-up removed the box under the pointer. Now the whole 30 px square around the box is clickable, a row is dragged only by its ⠿ handle, and a redraw waits until the mouse button is released
- **Faster conflict scan** (about 3x on a large mod list, same results): the file parser now tokenizes in C, per-file cache lookups use plain `os.stat`, and shared keys are grouped only when there is something to compare
- **Activity log** (test builds, or `MODMANAGER_ACTIVITY_LOG=1`): `RoninModManager-activity.log` records every request, scan, conflict check and update step with millisecond timestamps and durations, to find what is slow or stuck. See docs/19
- Removed unused imports and a leftover loop variable

## 0.8.4 - favourites, merge, library sort and tags, test builds
- **Test builds (nightly), experimental.** Settings -> App & updates -> Test builds installs the newest build of the branch being worked on, so changes can be tried before they become a release. A release is made from the exact commit that was tested (the release job warns if not). See docs/19
- **Favourites.** Star a mod (Library) or a playset (sidebar). Starred playsets stay at the top of the list; the library has "Favourites first" and a "★ Favourites only" button
- **Library sort by number of playsets:** "Most playsets first", with a "N playsets" count on every row
- **Merge:** in the Compare tab, "Merge both into a new playset" makes a new playset with every mod of both (this one's order first, a mod is enabled if it is enabled in either); neither playset is changed
- **Library sorting and tags.** Sort by Name, by Workshop then Local, by Tag, or (the new default) Workshop / Local and then tag, with a heading and count for each group (mods without tags last). A tag menu lists every tag with its count and shows only the mods that have it, and each row shows its first tags. The tags are read from each mod's own descriptor or metadata at every scan and also stored in the library file; your sort choice is remembered

## 0.8.3 - colour schemes and text size, No mods on top
- **Settings -> UI:** pick a colour scheme (Game look, Midnight, Parchment, Forest, Slate, Rose, High contrast) and a text size (Small to Extra large) for each game; "Use these for all games" copies them to the others
- The built-in "No mods" playset is now at the top of the sidebar
- In the load order a warning or error tag sits just left of the Workshop/Local tag, so that tag always ends the row

## 0.8.2 - Ronin Mod Manager, Europa Universalis V import, no empty playsets
- **New name: Ronin Mod Manager.** The window, installer, shortcuts and page titles use it. The app now keeps its data in `%APPDATA%\Ronin Mod Manager\` and its error log in `Documents\Ronin Mod Manager\RoninModManager-errors.log`. **Nothing is read from the old folders** (`modmanager`, `ck3mm`, `eu5mm`, `vic3mm`) any more, so this is a fresh start. The downloaded file names (`Mod-Manager-windows.exe`, `Mod-Manager-Setup.exe`) are unchanged so older copies can still update to this one
- **Europa Universalis V can import its launcher playsets.** The game keeps them in `playsets.json` in its folder in Documents (not in a database like the other games). Workshop and local mods are matched by their last folders, so it works on any drive and for any Windows user name
- **A built-in "No mods" playset instead of empty "Default" ones.** It is always listed under your playsets (pinned at the bottom of the sidebar), is never stored, and cannot be changed. Press Play on it to start the game with no mods, so you can tell whether a problem is a mod or the game or its launcher (Bannerlord still loads its official modules). A game with no playset of your own starts on it; the app no longer creates "Default" playsets by itself. Empty playsets called "Default" left by older versions are removed on start (a playset with mods, notes or an import origin is never touched)
- **Settings -> Erase all data (experimental)** deletes everything the app saved (playsets, library, backups, logos, presets, settings) after you type ERASE. The games' files, mods, saves and the error log are not touched
- The one-time copy of playsets from the old standalone managers (`ck3mm`, `eu5mm`, `vic3mm`) is removed

## 0.8.1 - fix the crash after updating
Fixes "No module named '_sqlite3'" that appeared when an older copy (0.5.0 and earlier) updated itself to 0.7.0 or 0.8.0. If you hit it, just start the app again; it works from then on.
- The old copy restarted the new one while still handing it its own unpacked files, which did not contain the database library the new version needs. The updater now starts the new copy with a clean environment so it unpacks its own files
- Reading the launcher's database no longer blocks the app from starting: if the database library is ever missing the app still opens and only the import reports a readable message
- Added tests for both
- Added `docs/18-more-games-plan.md`: the plan for Stellaris, Imperator: Rome, Civilization VI and Cities: Skylines (not built yet)
- macOS and Linux apps are not built for now (saved for later); releases contain the Windows app and installer

## 0.8.0 - Mount & Blade II: Bannerlord
Mount & Blade II: Bannerlord is now a supported game next to Crusader Kings III, Europa Universalis V and Victoria 3: its modules get playsets, dependency-aware auto-sort, one-click install from an archive and a Play button that starts the game with your module list.
- Modules are read from `<install>/Modules` and the Steam Workshop folder (SubModule.xml: required and optional dependencies, load-after rules, incompatible modules); official modules always load first
- A new playset starts with the official modules; Play runs `Bannerlord.exe /singleplayer _MODULES_*…*_MODULES_` with the enabled modules, or just a chosen part (Launch part…)
- The Import menu can bring in the launcher's last module selection (`LauncherData.xml`); Install mod… puts a module archive into `Modules` (official modules are never replaced)
- Not offered for this game because they do not apply: Conflicts tab, base-game comparison, save-version checks and per-playset save folders
- **Unverified on a real Bannerlord install**; docs/17-bannerlord.md lists what to check. Everything is built from other mod managers' open-source code and tested with fake installs
## 0.7.0 - import the playsets you already have
The new Import menu brings in the playsets that already exist in each game's own Paradox launcher, automatically when a game opens or on demand, so you do not rebuild them by hand. You can also hide the Import button if you do not use it.
- The launcher's database (`launcher-v2.sqlite`) is only ever read, from a temporary copy; load order, enabled/disabled state and the launcher's active playset are kept. Mods that are in a playset but not installed stay in it as "not installed" so they can be downloaded; mods that exist only on Paradox's own mod service are listed as not matched
- Pressing Import again adds only what is new (or what you deleted here); the automatic import never brings back a playset you deleted on purpose
- Settings → Playing has the same two switches (import automatically, show the Import button)
- New tests build launcher databases (including an older layout and a damaged file) and drive the menu in a browser
- Also in this release (version 0.5.1 was never published on its own): a mod folder Windows cannot open (WinError 448) no longer stops a whole game from loading; the error log moved to `Documents/Mod Manager/ModManager-errors.log`; a new app icon; eight Steam Workshop collections as ready-made presets (Victoria 3, Crusader Kings III, Europa Universalis V); the collection importer refuses a collection for another game; and every file the app reads or writes is now explicitly UTF-8, so names with accents or other scripts cannot break it on Windows

## 0.5.1 - one unreadable folder no longer breaks loading (shipped inside 0.7.0)
Fixes a crash where one mod folder Windows could not open stopped a whole game from loading, moves the error log into its own folder, and brings a new icon. It also adds eight Steam Workshop collections as ready-made presets (four for Victoria 3, three for Crusader Kings III, one for Europa Universalis V).


- Fixed: a mod folder Windows cannot open (for example a link or mount it does not trust, WinError 448) stopped the whole game from loading; such folders are now skipped, and a mod that points at one shows as missing
- The error log now lives in its own folder, `Documents/Mod Manager/ModManager-errors.log`; an older log in Documents is moved there
- New presets from Steam Workshop collections: Victoria 3 — Ultra Historical Mod Series, zw's Vic3 Mods, zw's Automated Vic3, Community Flavor Playlist; Crusader Kings III — Seastar's AGOT Collection, Small Maps, A Game of Thrones: The Definitive Collection; Europa Universalis V — Roman Empire Collection. `tools/make_preset.py` makes more from collection links
- Importing a collection now refuses one that belongs to another game and leaves out mods Steam has removed
- New app and installer icon (three stacked layers on indigo); `installer/make_icon.py` draws it
- New regression tests make each mod folder unreadable in turn, in every way a filesystem probe can fail, and check that loading, warnings, conflicts, the file tree and launching still work
- The same error repeated within 30 seconds is written once, and a window closed mid-answer is no longer reported as an error

## 0.5.0 - its own window
Mod Manager now opens in its own window instead of a browser tab, and "Check for updates" can download the new version and restart the app in one click.


- Opens in its own application window instead of a browser tab; closing the window quits the app. Windows and macOS use the system web view (WebView2 / WebKit) through pywebview; elsewhere an installed Edge, Chrome or Chromium is opened as a chromeless "app" window; the default browser is the last resort (`--browser` forces it)
- The Windows app has no console window and its own icon; startup failures are shown in a message box and written to the error log
- After an in-app update the new version opens its own window
- Settings → App & updates → **Check for updates now** now offers **Download and restart** (it no longer only links to the release page), with progress shown in the window
- Fixed: adding several mods quickly could silently lose one (changes now queue and each builds on the previous result)

## 0.4.0 - cleaner settings
The settings window is redesigned with side navigation, one card per topic, larger text and toggle switches, and there is now a Windows installer.


- Settings window redesigned: side navigation (Game, Storage, Playing, Downloads, App & updates), a card per topic, larger text, toggle switches and more spacing
- Windows installer (`Mod-Manager-Setup.exe`), MIT license, game logos always shown (downloaded once from Steam's public art if missing)

## 0.3.0 - downloadable, self-updating app
Mod Manager is now a downloadable app for Windows, macOS and Linux that can update itself from GitHub, and it writes problems to an error log you can send in.


- Single-file apps for Windows, macOS and Linux are built by CI and attached to each GitHub release with `SHA256SUMS.txt`
- **Update now**: the packaged app downloads the newest release, verifies the checksum, replaces itself and restarts (see docs/14)
- Error log in `Documents/ModManager-errors.log`; fixes for the "reading 'playsets'" error and logo flipping when switching games; conflict scanning moved off the critical path (faster loading)
- Compare tab no longer shows the previous comparison while loading

## 0.2.0 - the merge
One app for Crusader Kings III, Europa Universalis V and Victoria 3, replacing `ck3-mod-manager`, `eu5-mod-manager` and `vic3-mod-manager`.

- New `modmanager` package built on the VIC3 engine with a `Game` profile layer (`games.py`); per-game config, playsets, library, backups, theme
- Game switcher, setup dialog with install detection (Steam registry, libraries on any drive, renamed installs, pasted paths), per-game logos from the user's own files only
- Per-game load files (`dlc_load.json` / `content_load.json`) and entry styles; stub-game launch test for each game
- Conflicts: per-script-folder definition keys, `patch` kind for `INJECT:`, base-game comparison (lazy), `replace_path` also against the base game
- Metadata from `.metadata/`, `metadata/` or root `metadata.json`; `rel_type` or `type` relationships; dependencies by metadata id
- Cycles reported in manual mode too; damaged metadata reported per mod
- Presets (JSON) with a draft, **unverified** RICE stack for CK3; Workshop download via Steam page or optional steamcmd
- Presets: import a public Steam Workshop collection by link (one keyless request to api.steampowered.com, only when you press Import; nothing is downloaded); draft CK3 presets for Cultures Expanded and Princes of Darkness
- Conflicts: definition clashes now show which file each mod defines the key in
- Problems tab is now **Warnings**, with a gear that hides chosen kinds of warning (per game, saved in the browser)
- **Launch part…** starts the game with only the mods you tick (dependency helper; the playset is not changed)
- Install mods from `.tar`, `.tar.gz/.tgz`, `.tar.bz2`, `.tar.xz` as well as `.zip`, with the same safety rules (no links, scripts, traversal, bombs). `.7z`/`.rar` need non-standard-library code and are not supported
- Saves: by default every playset shares the game's normal save folder (a playset that had its own folder is un-linked on the next launch; its saves are kept where they were). "Own save folder" stays optional per playset
- Save-version guard: before starting, compares the game release (1.14 vs 1.15, patch releases ignored) with the one the saves were made on (read from the newest save's header when readable, otherwise the release of the last launch from this app) and asks before continuing. Setting: Settings -> warn about save versions
- Mod update check (Library tab, button only): Steam's last-updated time vs Steam's own local record; Workshop mods only
- Files tab: merged file tree of the playset with the winning mod per file; per-mod file tree in the details drawer showing what overrides what
- Fixed: Rescan on the Presets tab did not rescan the folders (installed counts stayed stale); preset ids re-checked against Steam's API, which caught and removed a wrong id ("Unique Building Plus")
- **Error log**: unexpected server errors, crashes and web-page script errors are written to `Documents/ModManager-errors.log` (follows OneDrive-redirected Documents); the page shows a red banner with the path
- Fixed: clicking while a game was still loading showed "Cannot read properties of null (reading 'playsets')"; switching games quickly could mix up logos/names (stale answers are now discarded)
- Faster: conflict scanning no longer blocks loading (load-order problems appear first, conflicts load behind), runs outside the global lock, file listing uses `os.scandir`, Windows drive probing limited to local drives
- Playsets imported (copied) from the standalone managers on first start; their share files still import; share files carry the game
- Enable all / disable all / prune; rolling `.bak` of the playset file; damaged playset file never overwritten
- App-wide settings split from per-game settings; `MODMANAGER_CONFIG_DIR`; `MODMANAGER_GITHUB_TOKEN`
- Dropped: bundled Paradox logo (CK3), automatic artwork fetch (EU5), the unapproved Tauri/Rust plan (CK3 docs)
- 244 unit/API/fuzz/stub-game tests, 4 browser end-to-end scripts; docs/00-13 rewritten for the merged app

Unverified on a real install: see docs/13-verification-checklist.md.

## Earlier history (standalone managers)
- VIC3 0.1.0: playsets, explained auto-sort, one-click fixes, conflicts, library, safe zip install, opt-in per-playset saves, update check, compare, CI
- EU5: install detection and setup dialog, base-game comparison, patch-aware conflicts, sharing
- CK3: Python prototype, drag-and-drop load order, file/definition conflicts
