# Moving from the standalone managers

`ck3-mod-manager`, `eu5-mod-manager` and `vic3-mod-manager` are superseded by this repository. **Nothing of yours is moved or deleted.**

## Playsets
The first time you open a game here, if it has no playsets yet, they are **copied** from the old manager's file:

| Game | Old file read |
|---|---|
| CK3 | `<config>/ck3mm/playsets.json` |
| EU5 | `<config>/eu5mm/playsets.json` |
| VIC3 | `<config>/vic3mm/playsets.json` |

(`<config>` = `%APPDATA%` on Windows, `$XDG_CONFIG_HOME` or `~/.config` elsewhere.) Mod ids are unchanged (`local:<name>`, `ws:<id>`), missing fields (notes, launch args, auto-sort) get defaults, and the Settings dialog says where your playsets came from. The old file is never modified, and later changes are made only in the new location, so you can keep using the old manager side by side if you like (the two will drift apart). Playset files already in the new location are never overwritten.

## Shared playset files
Files exported by the old managers (`vic3mm-playset`, `eu5mm-playset/1`) import fine into the matching game. Files exported here carry the game and are refused, with a clear message, by another game.

## What changed that you may notice
- One URL/port (`8765`) and one command (`python -m modmanager`, `--game` picks the game); the old per-game commands and ports are gone.
- EU5: base-game comparison and setup are the same; artwork is no longer fetched from Steam automatically (the logo comes from your Steam cache, your own file or `--fetch-logo`).
- CK3: the bundled Paradox logo is gone; definition conflicts are keyed per script folder (`common/traits: x`) instead of per top-level folder (`common: x`), which removes false positives; auto-sort, problems and conflicts use the newer engine.
- Update checks use `MODMANAGER_GITHUB_TOKEN` (was `VIC3MM_GITHUB_TOKEN`) and look at this repository.
- Config folder: `modmanager/<game>/` instead of `ck3mm/`, `eu5mm/`, `vic3mm/`.

## Retiring the old repositories
Do this yourself when you are happy: archive the three old repositories on GitHub (Settings -> Archive). Each one's README should say "moved to My-Mod-Manager".
