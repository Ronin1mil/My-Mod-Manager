# Playset files you can write by hand

A playset can be brought in from a **text list** or a **JSON file**. Both are easy to write yourself, in Notepad, or to have another AI write for you. Import them with the sidebar's **Import** button: *From a file* (a `.txt` or `.json` file) or *From a list* (paste the text).

Mods are found by their **Steam Workshop id** first, then by their **name** (capital letters do not matter). A mod that is not installed is skipped and named in the message after the import; install it and import again.

Where to find a Workshop id: it is the number at the end of the mod's Workshop page link, `https://steamcommunity.com/sharedfiles/filedetails/?id=`**`2217567218`**. Local mods (in `Documents/Paradox Interactive/<game>/mod`) have no id; use their name as the game's launcher shows it.

## 1. A text list (the simplest)

One mod per line, in load order (first line loads first):

```text
# Playset: My Big Campaign
# Game: ck3
https://steamcommunity.com/sharedfiles/filedetails/?id=2217567218
2216670956  Community Flavor Pack
My Local Tweaks
[off] 1234567890  Something I am testing
```

Rules:
- A line is a **Workshop link**, a **Workshop id** (a name after the id is only for people to read), or a **mod name**.
- Empty lines and lines starting with `#` are skipped.
- `# Playset: <name>` names the playset (the name typed in the Import window wins). `# Game: <id>` is optional; with it, the list is refused by another game. The ids are `ck3`, `eu4`, `eu5`, `vic3`, `hoi4`, `stellaris`, `imperator`, `bannerlord`.
- `[off]` in front adds the mod to the playset switched off.
- List bullets are fine: `- `, `* `, `• `, `1. `, `1) ` at the start of a line are ignored, so a list copied from a forum post or a Reddit comment usually works as it is.

**Playset settings → Export as text** writes exactly this format, so a list made by the app can be edited and imported again.

## 2. A JSON file

The smallest file that works:

```json
{
  "name": "My Big Campaign",
  "game": "ck3",
  "mods": [
    "https://steamcommunity.com/sharedfiles/filedetails/?id=2217567218",
    "2216670956",
    "My Local Tweaks"
  ]
}
```

Each entry in `mods` is either a **text** (read exactly like a line of the text list above, `[off]` included) or an **object**:

```json
{ "remote_id": "1234567890", "name": "Something I am testing", "enabled": false, "note": "crashes on start" }
```

| Field | Needed | Meaning |
|---|---|---|
| `name` (file) | no | the playset's name (60 characters at most; "Imported" if left out) |
| `game` | no | the game id (list above); a file for another game is refused |
| `mods` | **yes** | the mods, in load order (5000 at most) |
| `notes` | no | the playset's notes |
| `launch_args` | no | extra game start options, for example `"-debug_mode"` |
| `auto_sort` | no | `true` to keep the playset sorted automatically |
| `format`, `version` | no | `"modmanager-playset"` and `1`; Export writes them, a hand-made file may leave them out |
| `remote_id` (mod) | one of these two | the Workshop id (`workshop_id` works too) |
| `name` (mod) | one of these two | the mod's name; used when there is no id, or the id is not installed |
| `enabled` (mod) | no | `false` = in the playset, switched off (default `true`) |
| `note` (mod) | no | your note on the mod (300 characters at most), shown with ✎ in the list |

**Playset settings → Export** writes the full form of this file, which is a good starting point to copy.

## 3. Asking another AI to write one

Paste this, then your own request:

> Write a playset file for Ronin Mod Manager. Use the plain text format: one mod per line in load order; each line is a Steam Workshop link or the Workshop id followed by two spaces and the mod's name; start with `# Playset: <name>` and `# Game: <ck3|eu4|eu5|vic3|hoi4|stellaris|imperator|bannerlord>`; put `[off]` in front of a mod that should be in the playset but switched off; use `#` lines for comments. Only use Workshop ids you are sure of; if you are not sure, write the mod's exact name instead of an id.

Check what comes back: an AI can invent Workshop ids. A wrong id falls back to the name when there is one, and a mod the app cannot find is named in the message after the import, so nothing breaks.

## What is checked
Text lists are 512 KB at most and files 1 MB. Every field is checked, a file for another game is refused, and a file that fails creates nothing (docs/07-security.md).
