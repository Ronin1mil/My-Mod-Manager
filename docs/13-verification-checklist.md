# Verification checklist (needs a real install)

Everything the app does for a game is tested against fake installs. These are the facts only a real install can settle. When a check disagrees, fix `modmanager/games.py` (or `store.py`), update the pinned tests, and set `verified=True` for the game (docs/02 explains how).

**The easiest way to help:** press Play once, then send `Documents\Ronin Mod Manager\RoninModManager-<game>.log`. It already holds what the app found, what it wrote, what the game's files said before and after, and again 15 and 90 seconds later (see docs/21). Add `RoninModManager-errors.log` if something crashed.

## Where each game stands
| Game | Detection | Load file | Play | Saves per playset |
|---|---|---|---|---|
| Crusader Kings III | confirmed | confirmed | **confirmed** (starts `ck3.exe` with the 20 playset mods) | confirmed |
| Europa Universalis V | confirmed | confirmed (`playsets.json`) | **confirmed** | to confirm |
| Victoria 3 | confirmed | format fixed from a real file | **to confirm** | to confirm |
| Bannerlord | confirmed (version, modules) | none | **to confirm** | not used |

## Per game, five minutes
1. **Detection**: open the game. Does the setup dialog find the install and show the right version?
2. **Library**: are your local and Workshop mods all listed with the right names? (If one is missing: what does its metadata look like?)
3. **Play**: make a playset with 2-3 mods and press **Play** with Steam running. Does the game start without the Paradox launcher window? Does its mod list show exactly the playset's mods, in order? (Victoria 3, Bannerlord: this is the check still open.)
4. **Order**: reorder, Play again; does the in-game load order follow?
5. **Launch arguments**: add `-debug_mode` to a playset's arguments, Play; does the game receive it?
6. **Saves**: Play a playset with its own saves: the game's save list shows only that playset's saves. Play the playset that keeps the game's saves: the old saves are back and `save games (shared)` is gone.
7. **Conflicts**: pick two mods you know overlap. Does the winner shown match the game?
8. **Base-game comparison**: turn it on in Settings; are the "Base game" overrides sensible and the first analysis fast enough?

## Also
- Does `steam://url/CommunityFilePage/<id>` open the Workshop page in Steam? (Open in Steam)
- steamcmd (optional): does a download land in `<steamcmd dir>\steamapps\workshop\content\<app>\<id>` and get picked up?
- Bannerlord: does the launcher's `Configs\LauncherData.xml` exist on your PC? (It did not on the PC checked, so Import had nothing to offer.)
- Presets: the Workshop ids were checked on Steam but none was played. Tell us if one is wrong.
