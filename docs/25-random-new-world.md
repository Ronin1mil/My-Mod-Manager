# Random New World (beta), version 1.1.0

Plan and reasons: [24-random-new-world-plan.md](24-random-new-world-plan.md). This file says what was built and what is
**not yet checked on a real PC**. Code: `modmanager/rnw.py` (everything), `modmanager/rnw_fields.py` (a data table),
the tab in `static/app.js`, routes in `server.py` (see [12-api.md](12-api.md)).

## What the user sees
Tab **Random New World (beta)** right after **Crash help (beta)**, only when the game is Europa Universalis V.
- **Generator box:** where Random New World (RNW) was found and how; **Open generator** (its own window), **Choose folder...**
  (a folder with `rnw.cmd` in it; saved as the game's `rnw_dir` setting), **Refresh**. When it is not found the page says
  where to get it (Steam Workshop item 3829217331 or GitHub) and still lists the worlds in your mod folder.
- **Make a new world:** world type (continents, small continents, supercontinent, archipelago, islands, the wall), a seed
  (empty = random) or a pasted world code. One job at a time, with progress, the generator's own messages and Cancel.
- **Your worlds:** one card per world with name, tag, state (On / Off in this playset, Installed, Kept not installed, Code
  only), type, seed, generator version, game build, age, build time, and an expandable **Settings** list. Buttons:
  **Use this world**, **Turn off**, **Add to game**, **Remove from game**, **Copy code**.

## How it runs the generator
RNW has no web API. It has a command line (`rnw.cmd` on Windows, `RandomNewWorld --cli` elsewhere) that prints JSON, and a
window program. The manager:
- **finds it** in this order: the folder chosen in the tab; every Steam library's `workshop/content/3450310/3829217331`;
  `<user folder>/mod/rnw_exp_hub`. A folder counts when it holds `rnw.cmd` and/or a program named like `Random New World*.exe`
  / `RandomNewWorld*.exe` / `rnw*.exe` (uninstallers and crash handlers skipped). Three levels deep at most.
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
1. The window program's file name (the finder accepts `Random New World*.exe`, `RandomNewWorld*.exe`, `rnw*.exe`).
2. That `rnw.cmd worlds`, `world-code`, `world --install`, `add-world`, `remove-world` behave as in RNW's source, and the
   exact JSON of `worlds` (the code only needs `id`, `code`, `place`, `name`, `tag`; all optional).
3. That `world --install` writes into the same mod folder this app reads (the job warns when it does not).
4. That a world code from a real world decodes (the decoder is tested against the format described in RNW's source, not yet
   against a code from the real program). A code that does not decode is shown as a problem, not an error.
5. That EU5 accepts the playset (one world on, hub off) and starts a new 1337 campaign with it.
6. Windows security prompts for an unsigned generator program.
Please send: the output of `rnw.cmd find-game` and `rnw.cmd worlds` (replace your Windows user name with `<user>`), and the
error log if the tab shows a problem.

## Next steps (1.1.x)
Increments are the third number: 1.1.1, 1.1.2, ... until it works well on a real PC. Candidates: read the world's picture
(`preview.png`) as the card image, the generator's full settings (sliders) in the new-world form, queues of several worlds,
saves-by-world notes, and compare two worlds' settings.
