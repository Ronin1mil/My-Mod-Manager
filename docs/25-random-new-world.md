# Random New World (beta), version 1.1.0

Plan and reasons: [24-random-new-world-plan.md](24-random-new-world-plan.md). This file says what was built and what is
**not yet checked on a real PC**. Code: `modmanager/rnw.py` (everything), `modmanager/rnw_fields.py` (a data table),
the tab in `static/app.js`, routes in `server.py` (see [12-api.md](12-api.md)).

## What the user sees
Tab **Random New World (beta)** right after **Crash help (beta)**, only when the game is Europa Universalis V.
- **Generator box:** where Random New World (RNW) was found and how; **Open generator** (its own window), **Choose folder...**
  (a folder with `rnw.cmd` in it; saved as the game's `rnw_dir` setting), **Refresh**. When it is not found the page says
  asks the user to choose its folder and still lists the worlds in your mod folder.
- **Make a new world:** world type (continents, small continents, supercontinent, archipelago, islands, the wall), a seed
  (empty = random) or a pasted world code. One job at a time, with progress, the generator's own messages and Cancel.
- **Your worlds:** one card per world with name, tag, state (On / Off in this playset, Installed, Kept not installed, Code
  only), type, seed, generator version, game build, age, build time, and an expandable **Settings** list. Buttons:
  **Use this world**, **Turn off**, **Add to game**, **Remove from game**, **Copy code**.

## How it runs the generator
RNW has no web API. It has a command line (`rnw.cmd` on Windows, `RandomNewWorld --cli` elsewhere) that prints JSON, and a
window program. The manager:
- **does not search for it** (1.1.3). **Make a new map** asks the user to point to the folder where Random New World is installed
  (`POST rnw/folder {path}`). The chosen folder and every folder inside it is searched (up to 8 levels, 60,000 entries or 10 s, whichever comes first); when `rnw.cmd` is not there, the two folders above it are searched too (they can be the package's own folder; never a drive's top folder or the home folder), and the folder that really holds it is remembered. A folder counts when it holds `rnw.cmd`
  and/or a program named like `Random New World*.exe` / `RandomNewWorld*.exe` / `rnw*.exe` (uninstallers and crash handlers
  skipped). The answer is a report the page writes into its "What I'm doing" box: what was looked at, whether `rnw.cmd` and the
  window program were found, and whether maps can be made from there. A folder that holds the generator is remembered (setting
  `rnw_dir`); an empty answer forgets it. **Browse…** (`POST rnw/pick {what: generator|map, start?}` -> `{path, cancelled, error}`) opens the system's folder window through `modmanager/pickfolder.py` (on Windows PowerShell opens Explorer's own folder window, `IFileOpenDialog` with `FOS_PICKFOLDERS`, built with a small C# `Add-Type`, and falls back to the old `FolderBrowserDialog` only if that fails; for files `OpenFileDialog`; tkinter elsewhere; the title and start folder are passed in environment variables, never in the script text); choosing the generator's folder runs the check at once, choosing a map folder only fills the box. On the Make screen the folder box and **Browse…** are always on screen, also when a folder is remembered. A folder that fails the check does not make the app forget the one that works. The Steam Workshop folder is only *suggested* (`hint`), never used on its own.
- **runs commands** from an argument list, never a shell string. Because a `.cmd` file runs through `cmd.exe`, every word is
  checked first: values are letters, digits and `. _ : -` only; options are `--lowercase-words`; the only path passed
  (`--game-dir`) must not contain `% ^ & | < > " !` or control characters (otherwise it is left out and RNW finds the game itself).
- **commands used:** `worlds` (the library as JSON), `world-code --preset P [--seed N]`, `world CODE --install [--game-dir D]`
  (the long build; progress lines `[ 12%] start <stage>` are read from its output), `add-world ID`, `remove-world ID`.
  RNW's commands are not a promised interface; the JSON is read loosely (unknown keys ignored, missing keys tolerated), its own
  error text is shown, and a failing `worlds` falls back to listing the mod folder only.
- **Cancel** ends the process (on Windows with `taskkill /T /F`, so the build under `rnw.cmd` stops too).
- After a build or add, the mod folders are read again so the world is a normal mod in the Library at once. If RNW installed
  the world somewhere other than the mod folder this app reads, the job says so.
- Before a build: refuses when fewer than 2 GB are free where the mods are. Memory (about 7.5 GB) is RNW's own check.

## Where a world's settings come from
Each card says which sources it used ("read from ...").
1. **The world's own files:** `.metadata/rnw-library/world.json` inside the mod (RNW writes it into every world it builds):
   code, preset, seed, generator, game build, creation time, build seconds, name, and a `record` of the resolved settings.
   The record's layout belongs to RNW, so it is shown generically: nested values are flattened to `a.b.c  value`, with file
   manifests, hashes and long text left out.
2. **The world code:** `RNW1-XXXXX-...` is found in the mod's description (`short_description` in `.metadata/metadata.json`)
   when there are no files, or taken from the files. Decoded here (`decode_code`): preset, 64-bit seed (kept as text, not a
   number, because the page cannot hold it exactly), generator version, and every setting that differs from the world type's
   defaults, using the table in `rnw_fields.py`. The code has a 3-byte check, so a typo is reported.
3. **The generator's library:** `rnw.cmd worlds` also lists worlds that are not installed (`kept`, `code_only`), with name,
   tag, notes and stars.
4. **This app's record:** `rnw-worlds.json` in the game's data folder (`%APPDATA%\Ronin Mod Manager\eu5\`). Written when a
   world is made or added from the tab: state, preset, seed, code, changed settings, generator version, game version, time
   taken, where it was installed, and the generator's own summary. Capped at 500 worlds. Kept even if the world's mod is
   later removed, so the specs are not lost.

## Using a world in a playset
**Use this world** (`POST rnw/use`): adds the mod to the playset if it is not in it, turns it on, turns **every other RNW
world and the generator hub off** (RNW's rule: one world, hub disabled), moves it to the end, and adds any mod it depends on.
The playset's own rules still apply afterwards (auto-sort keeps a stable order). RNW's own note: Refined Colonization must load
before the world; with the world last that holds. Starting still goes through the normal Play button.

## Licence and what is shared
RNW is MPL-2.0 and is **not** bundled or copied. `rnw_fields.py` is data from its `worldcode.py` and stays MPL-2.0 (header in
the file). Generated worlds contain data derived from the game and are for local use only: they are not part of shared or
exported playsets.

## Not yet checked on a real PC (verify, then fix what differs)
1. ~~The window program's file name~~ Seen on a real PC (1.1.1 log): the Workshop copy holds `Random New World Generator.exe` and no `rnw.cmd`. Still open: where `rnw.cmd` is (the 1.1.3 log lists the generator's folder), and whether the standalone package from GitHub works with this app.
2. That `rnw.cmd worlds`, `world-code`, `world --install`, `add-world`, `remove-world` behave as in RNW's source, and the
   exact JSON of `worlds` (the code only needs `id`, `code`, `place`, `name`, `tag`; all optional).
3. That `world --install` writes into the same mod folder this app reads (the job warns when it does not).
4. That a world code from a real world decodes (the decoder is tested against the format described in RNW's source, not yet
   against a code from the real program). A code that does not decode is shown as a problem, not an error.
5. That EU5 accepts the playset (one world on, hub off) and starts a new 1337 campaign with it.
6. Windows security prompts for an unsigned generator program.
Please send: the output of `rnw.cmd find-game` and `rnw.cmd worlds` (replace your Windows user name with `<user>`), and the
error log if the tab shows a problem.

## The tab in 1.1.3: a menu first
The tab opens on a menu and reads the list of maps at once (`GET /api/eu5/rnw/files`, no program is started), so the menu lists them. It shows two choices: **Import my maps** (`GET /api/eu5/rnw/files`: finds the generator
by looking at folders and reads `mod\rnw_exp_world_*`, starts no program) and **Make a new map** (finds the generator, then
`rnw/new`). Importing: `POST /api/eu5/rnw/import` with `{path}` copies a map folder, or a folder holding several, into the mod
folder as a background job (copied under `<name>.importing`, renamed when complete; symlinks skipped; refuses a world already
there; checks free disk space) or with `{code}` remembers a world code in `rnw-worlds.json` (state `imported`). The generator's
own list (`rnw/list`) is only asked for when the user presses the button for it. **Found on a real PC:** the Workshop copy has
`Random New World Generator.exe` and no `rnw.cmd`; on Windows commands therefore need `rnw.cmd` (the window program is never
given `--cli`).

## The .rnworld map file (1.1.3)
Seen on a real PC: Random New World exports one map as `name.rnworld`, a **zip** holding `rnworld.json` (`kind: "world"`, `format: 1`,
`exported_by`, a SHA-256 of each file), `world.json` (the library record: `code`, `preset`, `seed` as a number, `generator`, `game_build`,
`created`, `seconds`, `name`, `notes`, `user_tag`, `id`, `mod_folder`, and `record` = the resolved settings, `algorithm`, the game
fingerprint), `atlas.json` (the map's country and province data for a preview, about 1 MB) and `atlas_labels.png`. It is the recipe and a
preview, not the 1.2 GB mod. `rnw.read_rnworld` reads only `rnworld.json` and `world.json` (64 KB and 2 MB limits, never extracted), checks
`kind`, `format` and the checksum of `world.json`; `Manager.import_rnworld` stores the map in `rnw-worlds.json` as state `imported` (name, tag,
notes, game build, time taken, the record as `summary`). `POST rnw/import {path}` takes a `.rnworld` file, a folder of them, or a map folder;
the window accepts a dropped file (the install route hands `.rnworld` to this, EU5 only). The code in the example file decodes (test) to
the preset, seed and every changed setting that its own record lists: the decoder matches the real program.

### The map inside the file
`atlas_labels.png` is not a picture to look at: every pixel is the number of its location, `red*65536 + green*256 + blue - 1` (black = open
sea), and `atlas.json` says what each location and country is. Checked on a real file (2128 x 2048 px, `scale` 4): `locations.centre` is `[row, column]`
and the pixel there decodes to the location's own index for 1996 of 2000 sampled locations. `atlas.json`: `countries[]` (`name`, `tag`,
`kind` state/tribe, `color`, `capital`, `culture`, `religion`, `locations`), `locations` as parallel lists (`kind` 0 land, 1 wasteland, 2 sea
zone, 3 lake; `owner` = index into `countries`, -1 none; `topography`, `vegetation`, `climate`, `culture`, `religion` = indexes into
`vocabulary`; `population`; `name`, a list `[kind, name]` for wasteland, sea and lake; also `area`, `centre`, `key`, `material`,
`settlement`, `complexity`), `vocabulary`, `size`, `scale`. On import the file is copied to `rnw-maps/<key>.rnworld` in the app's data folder
(`key` = first 16 hex of the SHA-256 of the world code; newest 60 kept). `GET rnw/map/<key>` answers the columns, the countries and a summary
(`MapStore.atlas`); `GET rnw/map/<key>.png` the picture. The page decodes the pixels into location numbers on a canvas and paints one colour per location for
the chosen layer; hovering reads the location under the pointer. No image library is needed on either side.

## Reading the log (1.1.1)
The app log (Tools > Open log folder) gets four `Random New World ...` lines whenever the tab is opened and something changed.
In the code each line has a `LOG-CHECK` comment saying what a good value looks like (`modmanager/rnw.py`, `Manager._diag`):
`generator:` (a folder with `rnw.cmd`), `worlds command:` (`ok=True`, keys such as id, code, preset, seed, place), `in the mod
folder:` (worlds with receipt and code) and `codes that did not decode:` (should be empty). A failed build also logs the
generator's last lines and exit code. Send that part of the log; the Windows user name is already replaced by `<user>`.

## Next steps (1.1.x)
Increments are the third number: 1.1.1, 1.1.2, ... until it works well on a real PC. Candidates: read the world's picture
(`preview.png`) as the card image, the generator's full settings (sliders) in the new-world form, queues of several worlds,
saves-by-world notes, and compare two worlds' settings.
