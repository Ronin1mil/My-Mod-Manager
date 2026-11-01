# UI design

Dark, one window, themed per game (colours come from `games.py`; switching the game in the sidebar recolours the whole UI):

```
+ Game ------------+------------------------------------------------+ Details ------+
| [Crusader Kings ▾]| Default        [x] Auto-sort [Install] [Refresh]| Alpha  v1.0  |
| PLAYSETS          | Load order | Library | Problems | Conflicts |    | deps: ...    |
| > Default      12 |   Compare | Presets                            | Why here?    |
|   Realism       8 | 1 [x] Core Library        local                 | Loads after  |
| [+New] [Import]   | 2 [x] Alpha (drag rows)   local   warning       | Core Library |
| ⚙ Settings  v0.2  |                                                  |              |
+-------------------+------------------------------------------------+--------------+
| Crusader Kings III 1.18 · 12 mods active · 1 error                    [ ▶ Play ]   |
+----------------------------------------------------------------------------------+
```
- **Game switcher** at the top of the sidebar; the choice is remembered (`localStorage`, falling back to the last game you launched) and can be deep-linked with `#ck3`, `#eu5`, `#vic3`, `#bannerlord`. Tabs: *Load order*, *Library*, *Warnings*, *Conflicts* (Paradox games only), *Files*, *Compare*, *Presets*. **Refresh** re-reads the current game; **Rescan** redoes start-up's work for every game. Right-click a playset for Open, Rename, Duplicate, Favourite, Settings, Delete.
- **Setup dialog** opens the first time a game has no known install (or from *Settings*): detected installs as radio buttons, a path box that validates as you type, user and Workshop folders, the base-game toggle, optional `steamcmd`, the update-check setting. *Skip* is remembered.
- **Pictures:** a mod's own `thumbnail.png` (found by `thumbs.py`: mod folder, `.metadata`, `metadata`; `GET /api/<game>/thumb/<mod id>`, `204` when there is none) shows as a card in the Library (**List** switches to rows), beside every row of the load order, large in the details drawer, and as the strip of active mods above the load order. No picture = a coloured tile with initials. Nothing is downloaded.
- **Loading screens:** `#boot` covers the window at start-up (names what it is doing); `#busy` covers the middle while another game opens and shows that game's logo. Both ignore the mouse and respect reduced motion.
- **Header:** Auto-sort, Install mod, Tools (Refresh, Rescan) and Playset settings.
- Big **Play** button always visible; confirms if the playset has errors. After Play the toast names the file written.
- **Load order** toolbar: enable all / disable all / prune uninstalled.
- **Conflicts** tab: chips by kind (File, Definition, Patch, Replace path, Localization) plus **Base game**; each row names the winner in green.
- **Presets** tab: each preset shows `verified`/`unverified`, how many mods are installed, and *Create playset*. After creating one, the not-installed mods are listed with *Open in Steam…*, *Download with steamcmd* (only if configured) and *Refresh*.
- Details drawer: description, tags, dependency status, "why is it here?", issues with fix buttons, location, uninstall.
- NEW / UPDATED badges (fade after a week); drop a `.zip` anywhere to install; `Ctrl+N` new playset.
- Untrusted text (mod names, descriptions, release notes) is always escaped; no inline scripts (CSP).
