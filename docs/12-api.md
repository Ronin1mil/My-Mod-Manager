# HTTP API

JSON over HTTP on `127.0.0.1` (default port 8765). Everything is same-origin only: requests must carry `Host: 127.0.0.1|localhost`, and a POST with an `Origin` header must match the host. Errors are `{"error": "..."}` with 400 (bad input, nothing changed), 403 (bad host/origin), 404, 413 (body too large) or 500.

## App-wide
| Route | |
|---|---|
| `GET /api/games` | games (id, name, app id, load file, theme, verified), app version, app settings, last known update result |
| `POST /api/custom-games` | (beta) `{game: {...}, id?}` adds a game or, with `id`, replaces one you added; the fields are checked (docs/20) -> the games list plus `id` |
| `POST /api/custom-games/remove` | (beta) `{id, erase_data?}` forgets a game you added; its saved playsets stay unless `erase_data` |
| `POST /api/settings` | `{auto_update_check?, dismissed_update?, last_game?}` (validated; unknown keys 400) |
| `POST /api/update-check` | `{force?}` -> release check result (cached 10 min) |

## Per game: `/api/<ck3|eu5|vic3>/...`
| Route | |
|---|---|
| `GET state` | mods, playsets, active, folders, game root/version, `has_logo`, `include_vanilla`, `setup_done`, `setup_needed`, steamcmd settings |
| `GET analyse/<playset>` | `{issues, notes, conflicts, counts, truncated}`; conflicts: `{kind: file\|definition\|patch\|replace\|localization, severity, path, mods, winner, vanilla?}` |
| `GET compare/<a>/<b>` | playset comparison with summaries |
| `GET playsets/<id>/share` | portable playset document (`modmanager-playset`, carries the game) |
| `GET presets` · `POST presets/<id>/apply` | list presets with installed counts · create a playset -> `{id, missing, status}` |
| `GET downloads` · `POST downloads` | steamcmd jobs · `{ids, method: "steam"\|"steamcmd"}` |
| `GET detect` · `GET inspect?path=` | installs found on this PC · validate a pasted path |
| `GET logo` | the user's own logo image, 404 if none |
| `POST paths` | `{game_dir?, user_dir?, workshop_dir?, include_vanilla?, steamcmd?, steam_user?}` (validated; sets `setup_done`) |
| `POST skip-setup` · `POST rescan` | remember "skip" · rescan mods (body `{"light": true}`, sent when the window gets focus: keeps everything already worked out if no mod changed; `state.scan_gen` grows whenever the mods changed) |
| `POST playsets` | `{name, mods?}` -> `{id}` |
| `POST playsets/<id>/` `update` `duplicate` `delete` `activate` `autosort` `enable` `enable_all` `disable_all` `prune` `save-preset` `launch` | playset actions (`update` takes name, mods, disabled, notes, launch_args, auto_sort, separate_saves; with auto-sort on, mods are re-sorted) |
| `POST import` | a shared playset document (game-checked) -> `{id, missing}` |
| `POST install` | raw `.zip` body, `X-Filename` header (streamed, 1 GB cap) |
| `POST mods/<id>/uninstall` | move a local mod to backups |
| `GET diagnose` | (beta) `{game, beta, checks: [{ok, label, detail}]}`: what was found and what was looked for |
