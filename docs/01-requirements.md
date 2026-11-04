# Requirements

Legend: [x] done and tested against fake installs; [ ] not done. "Confirmed" means checked on a real install (CK3 and EU5 are; see docs/22 for all four games).

## Done
- [x] Four games behind one switcher (CK3, EU5, VIC3, Bannerlord) plus games you add (beta); per-game config, playsets, library, theme
- [x] Detect install (Steam registry, every library in `libraryfolders.vdf`, hand-made libraries on other drives, renamed install folders via `appmanifest`), user dir, Workshop dir, game version; setup dialog with live validation; any path inside the install resolves to the root
- [x] Scan local + Workshop mods; read `.metadata/metadata.json`, `metadata/metadata.json`, `metadata.json`, `.mod` descriptors and Bannerlord `SubModule.xml`
- [x] Persistent library: new / updated / removed since last scan; **Rescan** redoes start-up's work while the app runs
- [x] Playsets: create, duplicate, rename, merge, delete, favourite, notes, launch arguments, export/import (game-checked), enable all / disable all / prune uninstalled, right-click menu
- [x] Per-mod enable/disable, drag-and-drop order, auto-sort with explanations
- [x] Warnings with one-click fixes: missing/disabled dependency, wrong order, loop, incompatible, duplicate, version mismatch, missing files, damaged metadata
- [x] Conflicts: file, definition (per script folder; `REPLACE:`/`INJECT:` aware), patch, replace_path, localization; base-game comparison
- [x] Presets (built-in, from Workshop collections, and your own); Workshop download via Steam page or optional steamcmd, with Steam rate-limit countdown
- [x] Install `.zip`/`.tar*` by drag and drop (safe extraction); uninstall into backups; upgrades keep the old version
- [x] Saves per playset (link-based, backup-first)
- [x] Play: writes what the game reads (CK3 `dlc_load.json`, EU5 `playsets.json`, VIC3 `content_load.json`, Bannerlord module list) and starts the game
- [x] Import the playsets the game's own launcher has (`launcher-v2.sqlite`, `playsets.json`, `LauncherData.xml`), read-only
- [x] Update check and self-update (Python edition `.pyzw`), nightly builds channel
- [x] Logs: errors, activity (nightly builds), and one log per game of what Play did
- [x] Compare two playsets

## Next
- [ ] Confirm Play on a real install for Victoria 3 and Bannerlord, and saves per playset for VIC3/EU5 (docs/13)
- [ ] More games (docs/18): Stellaris, Imperator: Rome, Civilization VI, Cities: Skylines
- [ ] `.7z` / `.rar` install
- [ ] Download progress from the Steam client (steamcmd jobs report progress; the Steam-page route cannot)
- [ ] Played-and-confirmed presets
- [ ] Workshop update notifications; Paradox Mods integration
