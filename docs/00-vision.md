# Vision

**"Mod Organizer 2 for Paradox grand strategy games, but simpler."** One better mod manager than the stock launcher, for every Paradox game the owner plays.

## Who it's for
Players who run several mod setups ("Vanilla+", "Realism", "Testing", "RICE") and want to switch between them in one click, see *why* two mods fight, and never hand-sort a load order again.

## Principles
1. **Simple first**: pick a playset, press Play. Everything else is secondary.
2. **Non-destructive**: never delete or overwrite the user's files. Uninstalls and upgrades go to a backup folder; the previous load file is kept as `.bak`; an existing save folder is moved aside, never removed; a damaged playset file is never overwritten.
3. **Explain, don't just flag**: every position in the load order has a "why is it here?" answer; every conflict names the winner; every problem says what to do.
4. **Honest about limits**: anything not verified against a real install is written down (docs/02, docs/13) and shown in the UI.
5. **Local and private**: no account, no telemetry, binds to 127.0.0.1 only; the network is touched only on an explicit user action.
6. **One engine, many games**: the engine never names a game; differences live in `games.py`.

## Non-goals (for now)
- Editing mod contents; being a Nexus / Paradox Mods replacement; multiplayer lobby management.
- Games outside Paradox's Clausewitz family. (Other Clausewitz games are a `games.py` entry plus verification.)
