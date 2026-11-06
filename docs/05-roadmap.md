# Roadmap

- [x] M1 Core: scan, descriptors/metadata, conflicts, playsets, load files
- [x] M2 Library and engine: persistent library, auto-sort with explanations, warnings + fixes
- [x] M3 Safety: validated inputs, safe install/uninstall, link-based saves, security headers, stub-game and browser tests
- [x] M4 UI: sidebar, tabs, details drawer, play bar, drag and drop install
- [x] M5 **Merge** of the CK3, EU5 and VIC3 managers into one app (0.2.0)
- [x] M6 Self-updating app, its own window (0.3-0.5), import of the launcher's playsets (0.7), Bannerlord (0.8), add-your-own-game beta and Python edition (0.9)
- [x] M7 **Verify on real installs**: CK3 and EU5 confirmed, files of all four read on a real PC (0.9.12, docs/22)
- [x] M7b Pictures, loading screen, in-app updates, start file, Workshop diagnostics (1.0.0-1.0.6)
- [x] M7c **Sort now** by overwrites, choose who wins a clash, Crash help (beta) (1.0.7-1.0.8)
- [x] M7d Random New World (beta, EU5), Victoria 3 launcher sync (1.1.0-1.1.3)
- [ ] M8 Confirm Play for Victoria 3 and Bannerlord; saves per playset for VIC3 and EU5
- [ ] M9 More games (docs/18): EU4, HOI4, Stellaris, Imperator built in (1.2.0, unverified); Civilization VI and Cities: Skylines not started
- [ ] M10 `.7z`/`.rar` (the standard library cannot read them; would need 7-Zip on the PC). Done in 1.2.0: the daily Workshop update notice (opt-in)
- [x] M11 Undo/Redo, restore deleted playsets, notes on mods, backup/restore, playset shortcuts, conflict folder filter and copy, lint in CI (1.2.0)

## Ideas for later (not planned yet; each needs a decision)
Grouped by what they help. Nothing here is promised; move an item into a milestone when it is picked.

**Safety and upkeep**
- CI: pin actions to commit SHAs (docs/07 known gap). (Moved to the Node 24 versions of the actions in 1.2.0.)
- Automatic backups: a backup (backup.py) once a day when the app starts, newest few kept, so nobody has to remember.
- A playset's history: list its Undo steps with what changed in each ("added 3 mods", "renamed"), and jump to one.

**Mods and conflicts**
- A compatibility patch from two clashing mods: write a small local mod that loads last and holds the chosen copy of each clashing file (Irony Mod Manager's "merge" does this for whole playsets).
- Export a playset's Workshop ids as a list someone can paste into Steam, and import such a list.
- Crash help: confirm on a real PC where each game keeps its logs (partly unverified, docs/23), and add log locations for games added with *Add a game*.

**Playing**
- Confirm Play for Victoria 3 and Bannerlord on a real PC (M8) and mark them verified.

**Reach**
- GOG installs: Irony Mod Manager knows the GOG ids of Stellaris (1508702879) and Imperator: Rome (2131232214); finding those installs would cover players without Steam.
- Confirm the four games added in 1.2.0 (EU4, HOI4, Stellaris, Imperator) on a real PC, then mark them verified.
- macOS and Linux builds again (the matrix entries are kept as a comment in `ci.yml`; docs/15).
- UI text in more languages (all text is in `app.js` today; would need a string table first).
