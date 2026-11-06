# Decisions

| # | Topic | Decision |
|---|---|---|
| 1 | Stack | Python stdlib + local web UI. No runtime dependencies. |
| 2 | One repo | `My-Mod-Manager` is the single home for CK3, EU5, VIC3 and Bannerlord. The three standalone repositories are superseded and point here. |
| 3 | Base engine | The VIC3 manager's engine (order engine, library, safe install, saves, compare, update check, security headers, CI) because it was the most complete and best-tested. EU5's install detection, setup dialog, base-game comparison, patches and sharing, and CK3's load-file export were ported in. |
| 4 | Games as data | Everything game-specific is a `Game` in `games.py`. The engine never names a game. |
| 5 | Per-game state | Separate config folder, playsets, library, backups and settings per game; app-wide settings (updates, last game) separate. |
| 6 | Source of truth | Our own `playsets.json`. The official launcher's sqlite is read for Import and, since 0.9.14, written for CK3 and VIC3 (docs/16); both also get the app's other playsets that the launcher lacks, by name: Steam starts CK3 through the Paradox launcher, which otherwise overwrites the app's playset. |
| 7 | Launch | Write what the game reads (its load file, EU5's `playsets.json`, Bannerlord's command line), then start the game: its own exe when the install says which one (CK3, VIC3, Bannerlord), else Steam; `--game-exe` wins. Nothing is marked verified until a real install confirms it. |
| 8 | Saves | Per-playset folders are **opt-in** (they touch user files and are unverified on a real install). |
| 9 | Archives | `.zip` only for now; executables/scripts are rejected outright (Paradox mods are data). |
| 10 | Auto-sort | On by default; manual order is preserved wherever no rule applies; turn off to get warnings instead. |
| 11 | Network | None by default. Allowed only on an explicit action: update check, `--fetch-logo`, "Open in Steam", steamcmd download. The EU5 manager's automatic artwork fetch from Steam was dropped. |
| 12 | Logos | Never stored in the repo (the CK3 manager's bundled Paradox logo was dropped). |
| 13 | Base-game comparison | On by default, parsed lazily so it stays cheap. |
| 14 | Definition scope | Keys clash only inside the same script folder (`common/traits`), not across folders. Finer than the old CK3 rule (whole `common/`) to avoid false positives. |
| 15 | Presets | Plain JSON, validated; shipped ids are labelled `unverified` until checked. No ids are invented: the draft RICE preset only contains ids read from Workshop page text. |
| 16 | Downloads | "Open in Steam" needs nothing; `steamcmd` is optional and never receives a password from this app. |
| 17 | Python edition | Releases carry only `Mod-Manager-python.pyzw` (run by the signed `py.exe`): Smart App Control blocks every unsigned exe and the files cannot be signed. Nightly builds still carry the exe and installer. |
| 18 | CK3 Tauri/Rust plan | The earlier CK3 plan (Tauri 2 + Rust + React) was never approved and is superseded by this app; its goals (conflict viewer, profiles, safety rules, security plan) are all covered here. |
| 19 | Names | Official versions are called **Version X.Y.Z** and nothing else. In-between versions are **nightly builds**, named only by their build id. The words "test build" are never used: releases are not tests, and no other names are invented (docs/19). A nightly copy is offered a newer official release before any newer nightly build. |
| 20 | More games | Europa Universalis IV, Hearts of Iron IV, Stellaris and Imperator: Rome are built in, with their folders and files taken from Irony Mod Manager's code (a maintained manager for the same games), not from memory. They stay `verified=False` until Play is confirmed on a real PC (docs/02). Crusader Kings II stays a template in Add a game: no other manager's code to check it against. |
| 21 | Undo | Every playset change keeps the playset as it was (30 steps per playset, saved in `playsets.json`, so they survive a restart); one user action is one step even when it saves twice (an edit and its auto-sort). Deleting keeps the playset in a list of the last 10 for Restore. |
| 22 | Backups | One `.zip` of the app's own JSON files only (no mods, saves or caches). Restoring is treated as untrusted input and saves the current data first, so a restore can itself be undone. |
| 23 | Mod update alerts | Opt-in only (decision 11): one Steam Web API request per game per day at most, when a game opens. The button in the Library still asks every time. |
