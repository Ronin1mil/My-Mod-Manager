# Presets and downloads

A **preset** is a named list of Workshop mods that turns into a normal playset in one click. A **download** gets missing Workshop mods onto your PC.

## Preset file
Plain JSON, one file per preset. Built-in presets live in `modmanager/presets/`, yours in `<config>/<game>/presets/` (a file with the same `id` overrides the built-in one). Broken files are skipped, never fatal.
```json
{
  "format": "modmanager-preset", "version": 1,
  "id": "ck3-rice-stack",            // lowercase letters, digits, - _ . (becomes the file name)
  "game": "ck3",                     // must match the game it is opened in
  "name": "RICE stack (draft)",
  "status": "unverified",            // "verified" only once someone confirmed the ids on a real install
  "description": "...", "source": "https://...",
  "mods": [
    {"workshop_id": "2273832430", "name": "RICE", "note": "optional", "enabled": true}
  ]
}
```
Limits: 1-300 mods, numeric ids, names/notes length-capped. Create one from a playset (*Playset settings -> Save as preset*, Workshop mods only) or write it by hand.

## Using one
*Presets* tab -> **Create playset**. The playset is made of `ws:<id>` entries in the preset's order; auto-sort then puts dependencies first. Mods you do not have show as "not installed" in *Warnings* and are listed under *Not installed yet*.

## The RICE stack
The built-in CK3 presets (`ck3-rice-stack`, `ck3-culture-expanded`, `ck3-princes-of-darkness`) are **unverified**: their ids were checked against Steam's Workshop API on 2026-10-29 (each exists, is public and belongs to Crusader Kings III), but nobody has played them. That check also caught a wrong id ("Unique Building Plus"), which was removed instead of guessed. Other companions named on the RICE page (CFP, compatibility patches) are not included because no id was confirmed; paste a Workshop collection link into the import box to add them.

## Bannerlord presets
Eight built-in presets, each made from a public Steam Workshop collection with `tools/make_preset.py` and checked on Steam on 2026-10-29 (every item exists and is public):

| Preset | Collection | Mods | What it is |
|---|---|---|---|
| `bannerlord-2026-essentials` | 3642838301 | 12 | small vanilla-plus set (RTS Camera/Command, Diplomacy, Better Time) |
| `bannerlord-immersive-vanilla` | 3493018660 | 14 | close to the base game: music, weather, banners, visuals |
| `bannerlord-every-player-should-have` | 3047704678 | 22 | broader vanilla-plus with Realistic Battle Mod |
| `bannerlord-2026` | 3814276546 | 22 | recent general pack (Better Bandits Plus, Distinguished Service) |
| `bannerlord-mods-of-bannerlord-war-sails` | 3716690126 | 39 | big War Sails-era pack (Calradia At War) |
| `bannerlord-realism` | 3125462668 | 40 | realistic and hardcore (RBM, De Re Militari, Culture Equipment Seeder) |
| `bannerlord-1-4-8-modpack` | 2941055735 | 47 | kingdoms and politics (Kingdom Politics Expanded, Machination) |
| `bannerlord-bannergourd` | 3615063246 | 50 | large stability-focused pack; its author marks it as on hiatus |

They are **unverified**: none was played, and most mods name 1.3 or 1.4 as their game version while the PC they were made on runs 1.5.6. A Workshop collection never lists the official modules, so creating a Bannerlord playset from a preset puts the installed official modules (`Native`, `SandBoxCore`, ...) first; Auto-sort then places the libraries (Harmony, ButterLib, UIExtenderEx, Mod Configuration Menu) before the mods that need them.

## Getting missing mods
1. **Open in Steam…** asks your Steam client to show each mod's Workshop page (`steam://url/CommunityFilePage/<id>`). Press **Subscribe**; Steam downloads into your normal Workshop folder. Then **Rescan**. (A subscription can only be made inside Steam; no app can do it for you.)
2. **Download with steamcmd** (optional): *Settings -> Downloading Workshop mods*: path to `steamcmd` and your Steam account name. Log in to steamcmd once yourself in a terminal (it caches the session); this app never sees or stores a password. Jobs run `steamcmd +login <account> +workshop_download_item <app> <id> +quit` one id at a time, with progress in the tab. Files land in steamcmd's own folder (`<steamcmd dir>/steamapps/workshop/content/<app>/<id>`); the tab tells you, and you add that folder as the Workshop folder in Settings so they are found. Many games only allow downloads from an account that owns them.

## Launching
Pressing **Play** (never automatic) writes the game's load file for the active playset and starts the game through Steam. Not-installed mods are skipped with the Warnings list explaining why. See docs/02 and docs/13 for what is unverified about the hand-off.
