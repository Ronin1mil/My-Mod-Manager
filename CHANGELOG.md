# Changelog

## 0.5.1 - one unreadable folder no longer breaks loading
Fixes a crash where one mod folder Windows could not open stopped a whole game from loading, moves the error log into its own folder, and brings a new icon.


- Fixed: a mod folder Windows cannot open (for example a link or mount it does not trust, WinError 448) stopped the whole game from loading; such folders are now skipped, and a mod that points at one shows as missing
- The error log now lives in its own folder, `Documents/Mod Manager/ModManager-errors.log`; an older log in Documents is moved there
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
