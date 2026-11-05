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
- [ ] M9 More games (docs/18)
- [ ] M10 `.7z`/`.rar`; tell the user when a Workshop mod in the active playset was updated (today only on *Check for updates* in the Library)

## Ideas for later (not planned yet; each needs a decision)
Grouped by what they help. Nothing here is promised; move an item into a milestone when it is picked.

**Safety and upkeep**
- Undo for playset edits: keep the last few versions of each playset (the store already writes a rolling `.bak` of the whole file), with an *Undo* next to the play bar.
- Backup and restore of all app data (playsets, settings, presets) as one file, for moving to a new PC.
- CI: pin actions to commit SHAs (docs/07 known gap) and move to the Node 24 versions of `actions/checkout` and `actions/setup-python` (CI now warns that Node 20 actions are forced onto Node 24).
- Lint in CI (`pyflakes`): cheap, catches unused imports and undefined names before a test does.

**Mods and conflicts**
- Mod update alerts (M10) using the existing per-mod tracking in `updates.py`, checked at most once a day and only when the user turns it on (decision 11: no network by default).
- Conflicts: filter by folder (`common/traits`, `gfx`, ...) and export the list as text for a mod author.
- Remember *why* a mod is disabled (a short note per mod per playset).
- Crash help: confirm on a real PC where each game keeps its logs (partly unverified, docs/23), and add log locations for games added with *Add a game*.

**Playing**
- Per-playset launch shortcuts: a desktop or Steam entry that starts the game with one playset.
- Confirm Play for Victoria 3 and Bannerlord on a real PC (M8) and mark them verified.

**Reach**
- macOS and Linux builds again (the matrix entries are kept as a comment in `ci.yml`; docs/15).
- UI text in more languages (all text is in `app.js` today; would need a string table first).
