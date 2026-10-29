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
*Presets* tab -> **Create playset**. The playset is made of `ws:<id>` entries in the preset's order; auto-sort then puts dependencies first. Mods you do not have show as "not installed" in *Problems* and are listed under *Not installed yet*.

## The RICE stack
`ck3-rice-stack` is a **draft**. RICE ("Regional Immersion and Cultural Enrichment", Workshop id `2273832430`) is a CK3 mod; the ids of the companions (EPE, VIET, Unique Building Plus, The Fallen Eagle) were read from Workshop page text on 2026-10-29 by an automated fetch whose output was inconsistent (it also claimed the pages were hidden/removed). **Treat every id as unconfirmed**: open each in Steam, check it is the right, current mod for your game version, and edit the file. Other well-known companions mentioned on the RICE page (CFP, Eastern Etiquette, Oriental Empires, compatibility patches) are intentionally *not* included because no id could be confirmed. If you meant a different set, send the Workshop collection link or the ids and it becomes a proper preset.

## Getting missing mods
1. **Open in Steam…** asks your Steam client to show each mod's Workshop page (`steam://url/CommunityFilePage/<id>`). Press **Subscribe**; Steam downloads into your normal Workshop folder. Then **Rescan**. (A subscription can only be made inside Steam; no app can do it for you.)
2. **Download with steamcmd** (optional): *Settings -> Downloading Workshop mods*: path to `steamcmd` and your Steam account name. Log in to steamcmd once yourself in a terminal (it caches the session); this app never sees or stores a password. Jobs run `steamcmd +login <account> +workshop_download_item <app> <id> +quit` one id at a time, with progress in the tab. Files land in steamcmd's own folder (`<steamcmd dir>/steamapps/workshop/content/<app>/<id>`); the tab tells you, and you add that folder as the Workshop folder in Settings so they are found. Many games only allow downloads from an account that owns them.

## Launching
Pressing **Play** (never automatic) writes the game's load file for the active playset and starts the game through Steam. Not-installed mods are skipped with the Problems list explaining why. See docs/02 and docs/13 for what is unverified about the hand-off.
