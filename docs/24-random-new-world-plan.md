# Random New World for Europa Universalis V: plan (version 1.1.0)

Status: **built in 1.1.0 as a first version (beta); changed in 1.1.1 to 1.1.3 after a real PC log (menu first, import, no `--cli` on the window program on Windows): see [25-random-new-world.md](25-random-new-world.md).** This file is the plan it came from. Written after reading Random New World's own documentation and command-line
source (links at the end). Nothing here has been run on a real PC: the generator is a Windows program and this was
written in a cloud session. Every "verify" item is listed at the bottom and has to be checked on a real install
(see the same method as [22-checked-on-a-real-pc.md](22-checked-on-a-real-pc.md)).

## What Random New World is
**Random New World (RNW)** is a separate program by Sir-Starch (GitHub `Sir-Starch/eu5-random-new-world`, licence
MPL-2.0, Steam Workshop item **3829217331**). It builds a new map for Europa Universalis V: the Old World stays as
Paradox made it, the Americas are replaced by generated continents, seas and native countries. **Every generated world
is its own ordinary EU5 mod**, a folder named `rnw_exp_world_<id>` inside the game's `mod` folder
(`Documents\Paradox Interactive\Europa Universalis V\mod`), with the usual `.metadata/metadata.json`. The world is
described by a short **world code** that can be shared and rebuilt.

Rules of the game side (from RNW's own notes):
- Start a **new 1337 campaign**; a generated map cannot be added to a running campaign.
- Enable **one** world mod at a time, and keep the Workshop item "Random New World" (the generator hub, folder
  `rnw_exp_hub`) **disabled** in the playset.
- **Restart EU5** before switching to another world.
- Keep the generated mod for as long as the saves made with it exist. A world code only stores the recipe, not a
  backup.
- Refined Colonization is supported with the order **Refined Colonization first, then the RNW world**.
- Each built world is about **1.2 GB** and building needs about **7.5 GB of free memory**; a build takes some minutes.
- The generated mods contain data derived from the game's own files: **local use only, never uploaded or shared**.

## Can the manager control it? Is there an "API"?
Short answer: **there is no web API and no library to import, but there is a proper command line that prints JSON.**
That is enough, and it is how we do it.

| Question | Answer |
|---|---|
| Can we launch the generator window? | Yes. The Workshop copy is a normal folder (`steamapps\workshop\content\3450310\3829217331`, EU5's "Open in folder" button opens it) and the standalone download is a folder from GitHub Releases. Both contain a launcher for the window and `rnw.cmd` for commands. We start the launcher like any program. **The launcher's exe name is not written in their docs: verify.** |
| Can we make worlds without opening the window? | Yes. `rnw.cmd world <CODE> --install` builds the world and puts the mod into the EU5 profile. `rnw.cmd world-code --preset <preset> --seed <n>` makes a code first. `rnw.cmd generate-queue codes.txt` builds many. Output is JSON (`code`, `bundle`, `installed`, `seconds`, `summary`). |
| Can we list "the maps I have"? | Yes, two ways. `rnw.cmd worlds` prints the library as JSON (`id`, `name`, `tag`, `code`, `preset`, `seed`, `game_build`, `place`, `notes`, `starred`, ...). `place` is `in_game` (installed), `kept` (a built copy kept in the library but not installed) or `code_only` (only the recipe). As a fallback that needs no generator at all, the manager already lists every `mod\rnw_exp_world_*` folder, because they are normal mods. |
| Can we add a world to the game? | Yes. `rnw.cmd add-world <id>` installs the kept mod, or rebuilds it from the code when only the code is left. It only writes into `mod\rnw_exp_*`; it never touches playsets or other mods. |
| Can we enable it for play? | That is **our** job, not theirs: RNW never edits playsets. After `add-world` the mod is in the `mod` folder, so the manager rescans, adds it to the playset, enables it, switches the other RNW worlds and the hub off, and orders it last (after Refined Colonization). |
| Is there a stable, documented interface? | The command names and the JSON of `worlds`, `world`, `add-world`, `find-game`, `remove-world` are in their open-source code, but they are **not promised as an API**; they changed between 1.0.0 and 1.1.0 (algorithm epoch 59 to 60). So the manager reads the JSON loosely (unknown keys ignored, missing keys tolerated), shows RNW's own error text when a call fails, and never relies on text output. The window talks to its own backend through a private JSON-lines bridge; **we do not use that**. |
| Does RNW need a login or network? | No. Everything is local. |
| Do we bundle or copy RNW? | **No.** It is a separate program under MPL-2.0 that the user installs (Workshop or GitHub). The manager only finds it and runs it. We never redistribute it or the worlds. |

## What the user will see (EU5 only)
A new page **Random New World** in the EU5 sidebar (hidden for the other games and when RNW is not found, where it
shows how to get it).

1. **Header:** where RNW was found (or "Not found: choose its folder" / "Get it from the Steam Workshop"), the EU5
   build it was made for against the installed build (warning when they differ), and the buttons **Open generator**
   (starts the window) and **New world**.
2. **List "Your worlds":** one card per world: name and tag, world type, seed, size on disk, whether it is installed,
   kept or code only, star and notes (read only), and status in this playset (Enabled / Off / Not in playset).
3. **Per world:** **Play this world** (adds if needed, enables it alone, turns the other worlds and the hub off,
   puts it last, then the usual Play flow with the reminder: "New 1337 campaign only, restart the game if another world
   was loaded"), **Add to game** (install only), **Enable / Disable in this playset**, **Remove from game** (RNW's
   `remove-world`, confirm first; keeps the library record and code).
4. **New world:** world type, seed (or paste a world code), a long-running job with elapsed time, a memory/disk check
   before it starts ("needs about 7.5 GB free memory and 1.2 GB disk"), a Cancel button, and the result added to the
   list. First version only passes `preset`/`seed`/code; the many fine settings stay in RNW's own window (the button
   opens it).
5. Worlds are **not** put in playset exports, shared playsets or presets (they are local, game-derived data); an
   exported playset names them as "your own RNW world" instead.

## How it is built
New module `modmanager/rnw.py` (about the size of `crash.py`), separate from `server.py`, with these parts:

- `find()`: looks, in order, at the folder the user chose in Settings; the Workshop folder
  `workshop\content\3450310\3829217331` in every Steam library the manager already knows; a local `mod\rnw_exp_hub`;
  and the usual standalone locations. Returns launcher exe, `rnw.cmd`, data directory (`%LOCALAPPDATA%\RandomNewWorld`
  or `portable.txt` / `RNW_DATA`). Pure and fast, no process started.
- `run(args)`: starts `rnw.cmd` with an **argument list, never a shell string** (same rule as `launch.py`). Because a
  `.cmd` file goes through `cmd.exe`, every value (world id, code, preset, seed, path) is checked against a strict
  pattern first (letters, digits, `-_.:`), so nothing like `& calc` can get through. Timeout, output size limit, JSON
  parsed with a fallback to the plain error text.
- `worlds()`: `rnw.cmd worlds` -> normalised list; if RNW or the command is unavailable, fall back to scanning
  `mod\rnw_exp_world_*` (name from `.metadata/metadata.json`, size, `in_game/map_data` present) so the page still works
  and says "limited view".
- `enable_world(playset, mod_id)`: pure playset change (the rules above), reusing the existing order code so
  dependencies and winners still hold; `Refined Colonization` placed before it when present.
- Heavy jobs (`world`, `add-world`) run like the existing background jobs in `server.py` (outside the data lock, with
  progress and cancel).
- Routes under `/api/eu5/rnw/...` (list, open, add, enable, remove, new, job status). Other games get 404.

Everything is beta and clearly labelled: "Random New World (beta)", because nothing is verified on a real PC yet.

## Tests
- A stub `rnw.cmd` / Python script in the test folder that prints the same JSON shapes as RNW, plus a version that
  fails, prints junk, hangs, and returns unknown extra keys. Tests cover: detection in fake Workshop and standalone
  folders, listing with all three `place` values, fallback scan, the injection checks, enabling one world and
  switching another off, order after Refined Colonization, the job with cancel, and 404 for other games.
- An end-to-end browser script for the page (list, play, enable, remove confirm).
- The naming guard test keeps passing (no forbidden wording).

## Version and branch
**1.1.0** (a new feature, so a minor version): `__version__`, a CHANGELOG section headed
"Random New World for Europa Universalis V (beta)", docs for the feature, pushed to `nightly` only. It becomes an
official release only when it is asked for ("release 1.1.0"). Until then it is a nightly build, named by its build id.

## Things I could not check (verify on a real PC before calling it done)
1. Name of the generator's launcher exe in the Workshop and standalone folders, and where Steam puts the Workshop copy
   on the user's machine.
2. Whether `rnw.cmd worlds` and `add-world` run when the generator window is closed and when it is open.
3. The exact values of `place` and the full JSON of `worlds` from the user's own library (ask the user to run
   `rnw.cmd find-game` and `rnw.cmd worlds`, with the Windows user name replaced by `<user>` before pasting).
4. Whether `world` prints progress lines we can show, or only the final JSON.
5. That EU5 accepts the playset the manager writes (hub off, one world on) and starts the new 1337 campaign.
6. Whether Windows security prompts (Smart App Control) block the unsigned generator when we start it; RNW's guide
   mentions this for unsigned Windows binaries.
7. Behaviour of the world mod list when the profile folder is in OneDrive Documents (the manager already handles a
   moved Documents folder; RNW says it does as well).

## Questions for the user
- Where is your Random New World installed: the Workshop copy, or a downloaded folder? (Decides the first search path.)
- Do you already have worlds built? The output of `rnw.cmd worlds` (and `find-game`) would settle items 1 to 4.
- Should **Play this world** also start the game, or only prepare the playset? (Plan: same as the normal Play button.)

## Sources
- RNW repository: https://github.com/Sir-Starch/eu5-random-new-world (README, `docs/generator-guide.md`,
  `docs/known-limitations.md`, `docs/architecture.md`, `docs/adr/0010-layered-worlds-and-a-generator-of-its-own.md`,
  `src/rnw/cli.py`, `src/rnw/cli_library.py`, `src/rnw/app/library.py`, `src/rnw/app/install.py`,
  `src/rnw/app/discovery.py`) read on 2026-11-04, RNW 1.1.0 for EU5 1.4.6.
- Steam Workshop item: https://steamcommunity.com/sharedfiles/filedetails/?id=3829217331
