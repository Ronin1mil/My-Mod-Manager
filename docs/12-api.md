# HTTP API

JSON over HTTP on `127.0.0.1` (default port 8765). Everything is same-origin only: requests must carry `Host: 127.0.0.1|localhost`, a POST with an `Origin` header must match the host, and any `/api/` request that Edge/Chrome mark `Sec-Fetch-Site: cross-site` or `same-site` (another website's link, `<img>` or script) is refused. Errors are `{"error": "..."}` with 400 (bad input, nothing changed), 403 (bad host/origin), 404, 413 (body too large) or 500.

## App-wide
| Route | |
|---|---|
| `GET /api/games` | games (id, name, app id, load file, theme, verified), app version, app settings, last known update result |
| `POST /api/custom-games` | (beta) `{game: {...}, id?}` adds a game or, with `id`, replaces one you added; the fields are checked (docs/20) -> the games list plus `id` |
| `POST /api/custom-games/remove` | (beta) `{id, erase_data?}` forgets a game you added; its saved playsets stay unless `erase_data` |
| `POST /api/settings` | `{auto_update_check?, dismissed_update?, last_game?}` (validated; unknown keys 400) |
| `POST /api/update-check` | `{force?}` -> release check result (cached 10 min) |
| `POST /api/self-update` · `GET /api/self-update` | start the checksum-verified update · its progress |
| `POST /api/full-rescan` | **Rescan**: start-up's work again for every game |
| `GET /api/ping` | the page is still open (keeps an app that runs in a browser window alive); no lock, no work |
| `GET /api/nightly` | the newest nightly build, for Settings -> Nightly builds |
| `POST /api/install-launcher` | Settings -> Install on this PC (Windows, Python edition): copy the app file to `%LOCALAPPDATA%` and write the start `.bat`; turns on install-on-start |
| `GET /api/backup` · `POST /api/restore-backup` | Settings -> App: the app's data as one `.zip` (download) · restore one (raw `.zip` body; every file checked first; the current data is saved in `app-backups/` before) -> `{restored, safety_copy, games}` |
| `GET /api/rescan-progress` | While Rescan runs: `{step, of, text}` for the progress bar |
| `POST /api/desktop-shortcut` · `POST /api/add-to-steam` | make the desktop icon (`{make: true}`) · add the app to Steam's non-Steam games (Steam closed) |
| `POST /api/erase-all` | Settings -> Erase all data (needs the typed word) |
| `POST /api/client-error` | the page reports a script error (goes to the error log) |

## Per game: `/api/<game id>/...` (`ck3`, `eu5`, `vic3`, `bannerlord`, or `cg-<name>` for a game you added)
| Route | |
|---|---|
| `GET state` | mods, playsets, active, folders, game root/version, `has_logo`, `include_vanilla`, `setup_done`, `setup_needed`, steamcmd settings |
| `GET analyse/<playset>` | `{issues, notes, conflicts, counts, truncated}`; conflicts: `{kind: file\|definition\|patch\|replace\|localization, severity, path, mods, winner, vanilla?}` |
| `GET conflicts/<playset>` | only the conflicts of that playset (worked out outside the lock) |
| `GET tree/<playset>` · `GET tree/<playset>/<mod id>` | the merged file list: for each path, the mod whose copy wins · one mod's files, each with the other enabled mods that also have it (later in the order wins) |
| `GET compare/<a>/<b>` | playset comparison with summaries |
| `GET playsets/<id>/share` | portable playset document (`modmanager-playset`, carries the game) |
| `GET presets` · `POST presets/<id>/apply` | list presets with installed counts · create a playset -> `{id, missing, status}` |
| `GET downloads` · `POST downloads` | steamcmd jobs · `{ids, method: "steam"\|"steamcmd"}` |
| `GET detect` · `GET inspect?path=` | installs found on this PC · validate a pasted path |
| `GET thumb/<mod id>` | the mod's own picture (png/jpg/webp/gif, 3 MB cap, links not followed); `204` when it has none; cached 5 min (ETag) |
| `GET logo` | the user's own logo image, 404 if none |
| `POST paths` | `{game_dir?, user_dir?, workshop_dir?, include_vanilla?, steamcmd?, steam_user?}` (validated; sets `setup_done`) |
| `POST skip-setup` · `POST rescan` | remember "skip" · rescan mods (body `{"light": true}`, sent when the window gets focus: keeps everything already worked out if no mod changed; `state.scan_gen` grows whenever the mods changed) |
| `POST playsets` | `{name, mods?}` -> `{id}` |
| `POST playsets/<id>/` `update` `duplicate` `delete` `activate` `autosort` `smartsort` `winner` `enable` `enable_all` `disable_all` `prune` `save-preset` `launch` `undo` `redo` `shortcut` | playset actions (`update` takes name, mods, disabled, notes, launch_args, auto_sort, separate_saves, saves_folder; with auto-sort on, mods are re-sorted; `autosort` is the dependency sort alone; `smartsort` also orders mods that overwrite each other and answers `{playset, report}`; `winner` takes `{pairs: [[winner, loser]], forget?}`, see docs/23) |
| `POST playsets/<id>/undo` · `redo` | one step back or forward in that playset's changes (400 when there is none) -> the playset. Every answer that is a playset carries `can_undo` / `can_redo` (steps available); so does each playset in `GET state` |
| `POST playsets/<deleted id>/restore` | bring back a deleted playset (`state.trash` lists the last 10: `{id, name, deleted, mods}`) -> `{id}` |
| `POST playsets/<id>/shortcut` | Windows: a desktop shortcut that runs `--game <id> --play <playset id>` -> `{made: true, path}`; elsewhere `{made: false, command}` |
| `GET playsets/<id>/share-text` | the playset as a text mod list -> `{name, text}` (docs/26) |
| `POST import` | a shared playset document (game-checked; `format` may be left out, a mod may be a plain text), or `{text, name?}` for a text mod list (docs/26) -> `{id, missing}` |
| `GET rnw/files` · `GET rnw/list` · `GET rnw/job` · `GET rnw/map/<key>[.png]` · `POST rnw/<action>` | Random New World (beta, **EU5 only**, others answer 400). `files` reads the mod folder and looks for the generator but starts **no program**; `list` is the same plus the generator's own `worlds` command (25 s limit) -> `{generator, hint, worlds[], cli, cli_used, notes, presets, hub, playset, job, free_gb}`; `job` -> `{job}` (polled); `map/<key>` -> the data of an imported `.rnworld` map (locations as columns, countries, vocabulary, `summary`), `map/<key>.png` -> its label picture (docs/25); actions `open` · `pick {what: generator|map|file, start?}` -> `{path, cancelled, error}` (opens the system's folder or file window; waits for the user) · `folder {path}` -> `{ok, generator, report[{ok, text}]}` (looks only in that folder; empty path forgets it) · `new {preset, seed?, code?}` · `import {path}` (a `.rnworld` file or a folder of them: remembered at once -> `{worlds[]}`; a map folder, or a folder of several: copied into the mod folder as a job -> `{job}`) or `import {code}` (remember a world code) · `add {id}` · `remove {id}` · `cancel` · `use {playset, folder, on?}` -> `{playset, did[]}` (docs/25) |
| `GET launcher` · `POST launcher/import` | the game launcher's playsets · import the chosen ones |
| `POST presets/import-collection` | turn a Steam Workshop collection into a preset |
| `POST mod-updates` · `POST downloads/retry` | check Workshop mods for updates (`{auto: true}`: the daily check, only with the setting on, at most once a day per game -> `{skipped, items}`) · retry a failed or rate-limited download |
| `POST playsets` | `{name, mods?, separate_saves?, saves_folder?}` makes a playset; `separate_saves` (default `true`) = it starts with a save folder of its own (no saves); `false` = it plays with the game's existing saves; `saves_folder` (a full path) = its own saves live in that folder (refused when it is, holds or is inside the game's save folder) |
| `POST pick-saves-folder` | `{start?}` opens the system's folder window (waits for the user) -> `{path, cancelled, error}` |
| `POST playsets/<id>/merge` · `saves-home` | merge playsets · make this playset the one that keeps the game's own saves |
| `POST fav-mod` · `POST ui` | favourite mods · remembered view settings |
| `POST install` | raw `.zip` body, `X-Filename` header (streamed, 1 GB cap) |
| `POST mods/<id>/uninstall` | move a local mod to backups |
| `GET diagnose` | (beta) `{game, beta, checks: [{ok, label, detail}]}`: what was found and what was looked for |
