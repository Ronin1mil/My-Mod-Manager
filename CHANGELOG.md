# Changelog

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
