# Crash help (beta) and choosing which mod wins

## Choosing which mod wins (Conflicts tab)
The Conflicts tab starts with **Mods that overwrite each other**: every pair of enabled mods that change the same file or
the same definition, the one that wins now (the one lower in the load order), how many files and definitions clash, and a
button **Make X win**. Pressing it moves the winner to load right after the loser (only as far as needed, dependencies
still hold) and remembers the choice in the playset (`winners`: `[[winner, loser], ...]`).

- **Sort now** honours the choices first, before every other rule (see `smartsort.py`).
- A choice that breaks a dependency is refused with the reason ("B needs A, so A has to load first and cannot win").
- A choice that contradicts another choice is refused until the other one is forgotten (the x next to "your choice").
- Dragging the list by hand so the loser loads last again cancels the choice; disabling or removing either mod forgets it.
- The pair list is worked out over all conflicts (the list below it is capped at 2000 rows). Intentional `REPLACE:`
  overrides and clashes with the base game are left out.

API: `POST /api/<game>/playsets/<id>/winner` `{pairs: [[winner, loser]], forget?: true}` answers the playset.

## Crash help (beta)
Tab **Crash help (beta)** -> **Diagnose last crash**. `GET /api/<game>/crash/<playset id>` (read-only) does this:

1. Finds the game's logs: `<user folder>/logs/*` and the newest folder of `<user folder>/crashes/` (for Bannerlord also
   `%PROGRAMDATA%\Mount and Blade II Bannerlord\logs` and `\crashes`). Reads the last 3 MB of up to 12 text files
   (`.log .txt .yml .json .xml .html`). `.dmp` files are not read.
2. Matches every error / warning line to the enabled mods it names: a mod folder or Workshop id in a path
   (`mod/<folder>/`, `workshop/content/<app>/<id>/`, `ugc_<id>`), else the mod's name (error lines only).
3. Names known crash causes: out of memory, stack overflow, access violation, graphics driver loss, a missing assembly
   (Bannerlord), a module built for another game version, a .NET exception, an unhandled exception.
4. Adds the app's own findings (missing / disabled dependency, incompatible mods, wrong game version, damaged metadata)
   and mods added or updated since the app last looked.
5. Ranks the mods: 3 points per distinct error line, 1 per warning (double near the end of a log or in a crash folder),
   2 / 1 for an app finding, 1.5 for a recently changed mod. *Most likely* needs a clear leader that the logs themselves name.

The result is clues, not proof. Buttons disable one suspect, or all likely ones, so the next Play shows whether it was them.
If the logs name nothing, the tab suggests halving the mods with **Launch part** on the Load order tab.

**Unverified:** where each game really writes its logs and what its crash folder holds. The list of files read is shown in
the result so a wrong guess is visible. Send `RoninModManager-<game>.log` (it records each diagnosis) and the log files
named in the result (remove your Windows user name first) to improve the patterns.
