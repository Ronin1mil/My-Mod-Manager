# Requirements

Legend: [x] done and tested against fake installs; [ ] not done. "Verified" means checked on a real install, which nothing is yet (see docs/13).

## Done
- [x] Three games behind one switcher, per-game config/playsets/library, per-game theme
- [x] Detect install (Steam registry, every library in `libraryfolders.vdf`, hand-made libraries on other drives, renamed install folders via `appmanifest`), user dir, Workshop dir, game version; setup dialog with live validation; any path inside the install resolves to the root
- [x] Scan local + Workshop mods; read `.metadata/metadata.json`, `metadata/metadata.json`, `metadata.json` and `.mod` descriptors (`rel_type` or `type` relationships, dependency ids)
- [x] Persistent library: new / updated / removed since last scan
- [x] Playsets: create, duplicate, rename, delete, notes, launch arguments, export/import (game-checked), enable all / disable all / prune uninstalled
- [x] Per-mod enable/disable, drag-and-drop order, auto-sort with explanations (name or metadata-id dependencies)
- [x] Problems with one-click fixes (enable dependency incl. transitive, auto-sort): missing/disabled dependency, wrong order, cycle, incompatible, duplicate, version mismatch, missing files, damaged metadata
- [x] Conflicts: file, definition (per script folder; `REPLACE:`/`INJECT:` aware), patch, replace_path, localization
- [x] Base-game comparison (lazy, only parses base files where a mod defines the same keys)
- [x] Presets (built-in + your own), Workshop download via Steam page or optional steamcmd
- [x] Install `.zip` by drag and drop (safe extraction); uninstall into backups; upgrades keep the old version
- [x] Per-playset save folders (opt-in, link-based, backup-first)
- [x] Play: per-game load file (+ backup), Workshop descriptor stubs where needed, Steam or `--game-exe`
- [x] Update check (manual / `--check-update` / on start, off by default)
- [x] Compare two playsets
- [x] Import playsets from the three standalone managers on first start

## Next
- [ ] Verify launch / load file / saves on a real install for each game (docs/13)
- [ ] `.7z` / `.rar` install
- [ ] Import from the stock launcher's playsets (`launcher-v2.sqlite`, read-only)
- [ ] Download progress from the Steam client (today: steamcmd jobs report progress; the Steam-page route cannot)
- [ ] Verified presets (needs someone with the game to confirm ids and load order)
- [ ] Single-file Windows `.exe` release (CI builds an unverified artifact)
- [ ] Workshop update notifications; Paradox Mods integration
