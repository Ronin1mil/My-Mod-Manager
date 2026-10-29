# Changelog

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
