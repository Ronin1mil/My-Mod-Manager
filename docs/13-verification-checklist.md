# Verification checklist (needs a real install)

Everything the app does for a game is tested against fake installs. These are the facts only a real install can settle. Each takes minutes. When a check disagrees, fix `modmanager/games.py` (or `store.mod_entry`), update the pinned tests, and set `verified=True` for the game (docs/02 explains how). **Please also send the file listings so the fixtures can match reality.**

## What to send (best way to help)
For each game: a `tree -L 3` / `dir /s /b` of the **install** folder (down to `game/`), of the **user** folder (`Documents/Paradox Interactive/<Game>`: `mod/`, load files, `launcher-v2.sqlite`, `save games/`), **one real mod's** `.metadata/metadata.json` and `.mod` stub, the **contents of the load file** if present (`dlc_load.json` / `content_load.json`), and `launcher/launcher-settings.json`. Remove personal paths first.

## Per game (CK3, EU5, VIC3)
1. **Detection**: open the game in the manager. Does the setup dialog find the install and show the right version? If not, what is the real marker folder?
2. **Library**: are your local and Workshop mods all listed with the right names? (If a mod is missing: what does its metadata look like?)
3. **Load file**: make a playset with 2-3 mods, press **Play**. Open the load file in the user folder. Is it the file the game really reads? Does the stock launcher leave it alone? (Start the game from the manager, then check the in-game mod list.)
4. **Order**: does the in-game load order match the playset? (Reorder, Play again, compare.)
5. **Workshop entries**: for a Workshop mod, does the game accept the entry we write (`mod/ugc_<id>.mod` or the path)? Did the created stub survive?
6. **Launch arguments**: add `-debug_mode`, Play; does the game receive it (`steam://run/<app>//<args>/`)?
7. **Saves**: Play a playset with its own saves: the game's save list shows only that playset's saves. Play the playset that keeps the game's saves: the old saves are back, and `save games (shared)` is gone.
8. **Conflicts**: pick two mods you know overlap. Does the winner shown match what you see in game?
9. **Base-game comparison**: turn it on; are the "Base game" overrides sensible, and is the first analysis fast enough?

## Also
- Windows: does the save link work as a junction without admin rights?
- Windows: does the PyInstaller `.exe` from CI start?
- Does `steam://url/CommunityFilePage/<id>` open the Workshop page in your Steam client?
- steamcmd (optional): does a download land in `<steamcmd dir>/steamapps/workshop/content/<app>/<id>` and get picked up after adding that folder?
- The draft RICE preset: are the five ids the right, current mods for your CK3 version? Update the file and flip its `status` to `verified`.
