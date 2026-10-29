# Importing the launcher's playsets

Paradox games (CK3, EU5, VIC3) keep their own playsets in the game's user folder, in `launcher-v2.sqlite` (or `launcher-v2_openbeta.sqlite`). Mod Manager can read them and create matching playsets of its own.

## What is read
`playsets` (name, active, removed), `playsets_mods` (which mods, enabled, position) and `mods` (Workshop id, Paradox mod id, descriptor name, folder, display name). The names come from the layout other mod managers read; older launcher versions lack some columns, so each column is optional. **Not verified against a current launcher on a real PC**: if the Import menu reports an error, send the error log.

The database is never opened in place: it (and its `-wal`/`-shm` side files) is copied to a temporary folder and read there, so the launcher and its playsets cannot be damaged and the launcher may stay open.

## How a launcher mod becomes one of ours
In this order: its Workshop id, its descriptor name (`mod/ugc_<id>.mod`, `mod/<name>.mod`), its folder, its display name. A Workshop mod that is not installed is kept in the playset as `ws:<id>` (shown as "not installed", downloadable like any preset mod). A mod that exists only on Paradox's own mod service (no Workshop id) cannot be matched and is reported in the result.

## Import menu (sidebar, **Import**)
- **From the launcher**: lists its playsets with a switch each (new ones are on). **Import** creates them. Pressing it again skips playsets already here, brings back one you deleted, and picks up new ones.
- **From a file**: the shared playset files made by *Export*.
- **Preferences**: *Import launcher playsets automatically* (default on) and *Show the Import button* (default on). Both are also in Settings → Playing.

## Automatic import
When a game opens (and right after its first setup), launcher playsets that were **never offered before** are imported. The app remembers which ones it has offered, so a playset you deleted on purpose does not return by itself; the Import button can still bring it back. If the app only had an empty playset, the launcher's active playset becomes the active one.
