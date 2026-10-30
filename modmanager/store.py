"""Playset persistence (JSON), sharing, and export to the game's load file (dlc_load.json / content_load.json)."""
import json
import os
import shutil
import time
import uuid
from pathlib import Path

from .launch import validate_launch_args
from .paths import config_dir

NO_MODS_ID = "nomods"  # the built-in playset that starts the game with no mods (never stored)
SHARE_FORMAT = "modmanager-playset"
LEGACY_SHARE = {"vic3mm-playset": "vic3", "eu5mm-playset/1": "eu5"}  # files from the standalone managers

MAX_NAME, MAX_NOTES, MAX_MODS = 60, 2000, 5000
DEFAULTS = {"notes": "", "launch_args": [], "auto_sort": True, "separate_saves": False, "favorite": False}


# per-game settings (folders + base-game comparison); app-wide ones live in GlobalSettings
SETTINGS_DEFAULTS = {"game_dir": "", "user_dir": "", "workshop_dir": "", "include_vanilla": True,
                     "setup_done": False, "steamcmd": "", "steam_user": "", "save_version_check": True,
                     "ui_scheme": "default", "ui_text": "normal"}
UI_SCHEMES = ("default", "midnight", "parchment", "forest", "slate", "rose", "contrast")
UI_TEXT = ("small", "normal", "large", "xlarge")
GLOBAL_DEFAULTS = {"auto_update_check": False, "dismissed_update": "", "last_game": "", "fetch_logos": True,
                   "auto_import_launcher": True, "show_import_button": True}


def _defaults():
    return {k: list(v) if isinstance(v, list) else v for k, v in DEFAULTS.items()}


def validate_name(name):
    name = "".join(c for c in str(name) if c.isprintable()).strip()
    if not name or len(name) > MAX_NAME:
        raise ValueError(f"A playset name must be 1-{MAX_NAME} characters.")
    return name


def _id_list(v, what):
    if not isinstance(v, list) or len(v) > MAX_MODS or not all(isinstance(x, str) and len(x) < 300 for x in v):
        raise ValueError(f"'{what}' must be a list of mod ids.")
    return list(dict.fromkeys(v))  # de-duplicate, keep order


def _atomic_write(path, text):
    tmp = path.with_suffix(f".{uuid.uuid4().hex[:8]}.tmp")
    tmp.write_text(text, encoding="utf-8")
    tmp.replace(path)


NO_MODS_NOTE = ("Starts the game with no mods, so you can tell whether a problem comes from a mod or from the game or its "
                "launcher. It is always here and cannot be changed; press + New to make a playset of your own.")


class Store:
    no_mods_provider = None  # () -> mod ids the built-in playset still needs (Bannerlord's official modules)

    def __init__(self, path=None, game=None):
        self.path = Path(path) if path else config_dir(game) / "playsets.json"
        self.data = {"active": None, "playsets": {}, "settings": {}}
        if self.path.is_file():
            try:
                d = json.loads(self.path.read_text(encoding="utf-8-sig"))
            except ValueError as e:  # never wipe a damaged file: the user may want to repair it
                raise ValueError(f"The playset file {self.path} is damaged ({e}). It was left untouched; "
                                 f"a backup may exist next to it ({self.path.with_suffix('.bak').name}).")
            if not isinstance(d, dict) or not isinstance(d.get("playsets", {}), dict):
                raise ValueError(f"The playset file {self.path} does not look like a playset file.")
            self.data.update(d)
            self.data.setdefault("settings", {})

    def settings(self):
        return {**SETTINGS_DEFAULTS, **{k: v for k, v in self.data.get("settings", {}).items() if k in SETTINGS_DEFAULTS}}

    def update_settings(self, **fields):
        """Per-game settings. Unknown keys and wrong types are rejected; nothing is applied unless all are valid."""
        clean = {}
        for k, v in fields.items():
            if k not in SETTINGS_DEFAULTS or not isinstance(v, type(SETTINGS_DEFAULTS[k])):
                raise ValueError(f"Invalid setting '{k}'.")
            if isinstance(v, str) and len(v) > 1000:
                raise ValueError(f"Invalid value for '{k}'.")
            if (k == "ui_scheme" and v not in UI_SCHEMES) or (k == "ui_text" and v not in UI_TEXT):
                raise ValueError(f"Invalid value for '{k}'.")
            clean[k] = v
        self.data.setdefault("settings", {}).update(clean)
        self.save()
        return self.settings()

    def save(self):
        if self.path.is_file():  # one rolling backup so a bad edit is recoverable
            shutil.copyfile(self.path, self.path.with_suffix(".bak"))
        _atomic_write(self.path, json.dumps(self.data, indent=2))

    def create(self, name, mods=None, disabled=None, **extra):
        pid = uuid.uuid4().hex[:8]
        ps = {"id": pid, "name": validate_name(name), "mods": _id_list(mods or [], "mods"),
              "disabled": _id_list(disabled or [], "disabled"), "created": int(time.time()), **_defaults(),
              "separate_saves": True}   # a new playset starts with its own saves; older ones keep what they had
        self.data["playsets"][pid] = ps
        if extra:
            try:
                self.update(pid, **extra)
            except ValueError:
                del self.data["playsets"][pid]
                raise
        self.data["active"] = self.data["active"] or pid
        self.save()
        return pid

    def set_origin(self, pid, origin):
        """Remember where a playset came from (for example 'launcher:<id>') so it is not imported twice."""
        self.get(pid)["origin"] = str(origin)[:200]
        seen = self.data.setdefault("launcher_seen", [])
        if str(origin).startswith("launcher:") and origin not in seen:
            seen.append(origin)
            del seen[:-500]
        self.save()

    def launcher_seen(self):
        return set(self.data.get("launcher_seen", []))

    def no_mods(self):
        mods = list(self.no_mods_provider()) if self.no_mods_provider else []
        return {"id": NO_MODS_ID, "name": "No mods", "mods": mods, "disabled": [], "created": 0, "virtual": True,
                **{**_defaults(), "notes": NO_MODS_NOTE, "auto_sort": False}}

    def get(self, pid):
        if pid == NO_MODS_ID:
            return self.no_mods()
        ps = self.data["playsets"][pid]
        for k, v in _defaults().items():
            ps.setdefault(k, v)
        return ps

    def update(self, pid, **fields):
        if pid == NO_MODS_ID:
            raise ValueError("The built-in 'No mods' playset cannot be changed. Press + New to make a playset of your own.")
        ps = self.get(pid)
        clean = {}
        if "name" in fields:
            clean["name"] = validate_name(fields["name"])
        for k in ("mods", "disabled"):
            if k in fields:
                clean[k] = _id_list(fields[k], k)
        if "notes" in fields:
            if not isinstance(fields["notes"], str) or len(fields["notes"]) > MAX_NOTES:
                raise ValueError(f"Notes can be at most {MAX_NOTES} characters.")
            clean["notes"] = fields["notes"]
        if "launch_args" in fields:
            clean["launch_args"] = validate_launch_args(fields["launch_args"])
        for k in ("auto_sort", "separate_saves", "favorite"):
            if k in fields:
                if not isinstance(fields[k], bool):
                    raise ValueError(f"'{k}' must be true or false.")
                clean[k] = fields[k]
        ps.update(clean)  # nothing is applied unless every field validated
        self.save()
        return ps

    def duplicate(self, pid, name):
        src = self.get(pid)
        return self.create(name, src["mods"], src["disabled"], notes=src["notes"],
                           launch_args=src["launch_args"], auto_sort=src["auto_sort"])

    def delete(self, pid):
        if pid == NO_MODS_ID:
            raise ValueError("The built-in 'No mods' playset cannot be deleted.")
        self.data["playsets"].pop(pid, None)
        if self.data["active"] == pid:
            self.data["active"] = next(iter(self.data["playsets"]), None)
        self.save()

    def replace_mod(self, old, new):
        """Every playset that lists `old` lists `new` in its place (same position, same on/off), or only keeps `new` where
        it already had both. -> how many playsets changed."""
        n = 0
        for ps in self.data["playsets"].values():
            if old not in ps["mods"]:
                continue
            had = new in ps["mods"]
            ps["mods"] = [m for m in ps["mods"] if m != old] if had else [new if m == old else m for m in ps["mods"]]
            off = old in ps["disabled"]
            ps["disabled"] = [m for m in ps["disabled"] if m != old] + ([new] if off and not had and new not in ps["disabled"] else [])
            n += 1
        if n:
            self.save()
        return n

    def merge(self, a, b, name):
        """A NEW playset with everything of `a` in its order, then what only `b` has (in b's order). A mod is enabled
        if it is enabled in either. Neither playset is changed."""
        pa, pb = self.get(a), self.get(b)
        order = list(pa["mods"]) + [m for m in pb["mods"] if m not in pa["mods"]]
        on = {m for ps in (pa, pb) for m in ps["mods"] if m not in ps["disabled"]}
        return self.create(name, order, [m for m in order if m not in on], notes=f"Merged from '{pa['name']}' and '{pb['name']}'.")

    def set_favorite_mod(self, mid, on):
        """Star or unstar a mod (kept in the playset file, so it survives rescans and uninstalls)."""
        mid = str(mid)
        if not mid or len(mid) > 300:
            raise ValueError("Invalid mod.")
        fav = self.data.setdefault("fav_mods", [])
        if on and mid not in fav:
            if len(fav) >= 5000:
                raise ValueError("Too many favourites.")
            fav.append(mid)
        elif not on and mid in fav:
            fav.remove(mid)
        self.save()
        return list(fav)

    def prune_empty_defaults(self):
        """Older versions made an empty playset called 'Default' whenever a game had none. Remove those leftovers (empty,
        no notes, not imported from anywhere); a playset the user named or filled is never touched. -> how many."""
        gone = [k for k, ps in self.data["playsets"].items()
                if ps.get("name") == "Default" and not ps.get("mods") and not ps.get("notes") and not ps.get("origin")]
        for k in gone:
            del self.data["playsets"][k]
        if gone:
            if self.data["active"] not in self.data["playsets"]:
                self.data["active"] = next(iter(self.data["playsets"]), None)
            self.save()
        return len(gone)

    def export(self, pid, mods):
        """Return enabled mod ids in load order for a playset (skipping disabled/unknown)."""
        ps = self.get(pid)
        return [m for m in ps["mods"] if m not in ps["disabled"] and m in mods]

    def share(self, pid, mods, game_id=""):
        """Portable playset description: mods are identified by workshop id or name, not local ids."""
        ps = self.get(pid)
        items = []
        for mid in ps["mods"]:
            m = mods.get(mid)
            rid = (m["remote_id"] if m else None) or (mid[3:] if mid.startswith("ws:") else None)
            items.append({"name": m["name"] if m else mid, "remote_id": rid,
                          "enabled": mid not in ps["disabled"]})
        return {"format": SHARE_FORMAT, "version": 1, "game": game_id, "name": ps["name"], "notes": ps["notes"],
                "launch_args": ps["launch_args"], "auto_sort": ps["auto_sort"], "mods": items}

    def import_shared(self, data, mods, game_id=""):
        """Create a playset from share() output (or a standalone-manager file). Returns (id, [names not installed])."""
        if not isinstance(data, dict):
            raise ValueError("Not a playset file")
        fmt = data.get("format")
        legacy_game = LEGACY_SHARE.get(fmt)
        if fmt != SHARE_FORMAT and legacy_game is None:
            raise ValueError("Not a playset file")
        file_game = data.get("game") or legacy_game
        if game_id and file_game and file_game != game_id:
            raise ValueError(f"This playset is for '{file_game}', not '{game_id}'. Open that game first.")
        items = data.get("mods")
        if not isinstance(items, list) or len(items) > MAX_MODS or not all(isinstance(i, dict) for i in items):
            raise ValueError("Playset file has an invalid mod list.")
        by_rid = {str(m["remote_id"]): m["id"] for m in mods.values() if m["remote_id"]}
        by_name = {m["name"]: m["id"] for m in mods.values()}
        order, off, missing = [], [], []
        for it in items:
            rid, nm = it.get("remote_id"), it.get("name")
            if not (rid is None or isinstance(rid, (str, int))) or not (nm is None or isinstance(nm, str)) \
                    or not isinstance(it.get("enabled", True), bool):
                raise ValueError("Playset file has an invalid mod entry.")
            mid = (by_rid.get(str(rid)) if rid is not None else None) or by_name.get(nm)
            if mid is None:
                missing.append(it.get("name") or str(it.get("remote_id")))
                continue
            order.append(mid)
            if not it.get("enabled", True):
                off.append(mid)
        extra = {k: data[k] for k in ("notes", "launch_args", "auto_sort") if k in data}
        return self.create(data.get("name") or "Imported", order, off, **extra), missing


class GlobalSettings:
    """App-wide settings (update checks, last game), shared by all games."""

    def __init__(self, path=None):
        self.path = Path(path) if path else config_dir() / "settings.json"
        self.data = {}
        try:
            d = json.loads(self.path.read_text(encoding="utf-8-sig"))
            if isinstance(d, dict):
                self.data = d
        except (OSError, ValueError):
            pass

    def get(self):
        return {**GLOBAL_DEFAULTS, **{k: v for k, v in self.data.items() if k in GLOBAL_DEFAULTS}}

    def update(self, **fields):
        clean = {}
        for k, v in fields.items():
            if k not in GLOBAL_DEFAULTS or not isinstance(v, type(GLOBAL_DEFAULTS[k])):
                raise ValueError(f"Invalid setting '{k}'.")
            if isinstance(v, str) and len(v) > 40:
                raise ValueError(f"Invalid value for '{k}'.")
            clean[k] = v
        self.data.update(clean)
        _atomic_write(self.path, json.dumps(self.data, indent=2))
        return self.get()


def mod_entry(game, m):
    """How the game's load file names a mod. 'descriptor' games list mod/<x>.mod stubs; 'path' games list the
    mod folder (local) or its Workshop folder; 'enabled_paths' games list {"path": <absolute folder>} for both."""
    if game.load_style == "enabled_paths":
        return {"path": os.path.normpath(m["root"])}
    if game.load_style == "path":
        return f"mod/{Path(m['root']).name}" if m["source"] == "local" else m["root"]
    if m["source"] == "workshop" or (m["remote_id"] and m["id"].startswith("ws:")):
        return f"mod/ugc_{m['remote_id']}.mod"
    return f"mod/{m['id'].split(':', 1)[1]}.mod"


def ensure_descriptor_stub(game, user_dir, m):
    """Workshop mods need a mod/ugc_<id>.mod pointing at the workshop folder (descriptor-style games);
    create it if the Paradox launcher never has."""
    if game.load_style != "descriptor" or m["source"] != "workshop":
        return False
    f = Path(user_dir) / mod_entry(game, m)
    if f.is_file():
        return False
    f.parent.mkdir(parents=True, exist_ok=True)
    root = m["root"].replace("\\", "/")
    f.write_text(f'name="{m["name"].replace(chr(34), "")}"\npath="{root}"\n'
                 f'remote_file_id="{m["remote_id"]}"\n', encoding="utf-8")
    return True


def write_load_file(game, user_dir, mods, ids, name=None):
    """Write the game's load file (what it reads at startup), backing up the previous one. `name` is the playset's name,
    used by games that start with a playset of their own list."""
    user_dir = Path(user_dir)
    for mid in ids:
        ensure_descriptor_stub(game, user_dir, mods[mid])
    f = user_dir / game.load_file
    cur = {}
    if f.is_file():
        try:
            cur = json.loads(f.read_text(encoding="utf-8-sig"))
        except ValueError:
            cur = {}
        if not isinstance(cur, dict):
            cur = {}
        shutil.copy2(f, f.with_suffix(".json.bak"))
    if game.load_style == "enabled_paths":
        cur["enabledMods"] = [mod_entry(game, mods[mid]) for mid in ids]
        cur.setdefault("enabledUGC", [])
        cur.setdefault("disabledDLC", [])
    else:
        cur["enabled_mods"] = [mod_entry(game, mods[mid]) for mid in ids]
        cur.setdefault("disabled_dlcs", [])
    _atomic_write(f, json.dumps(cur, indent=2))
    if game.playsets_file:
        write_launcher_playset(game, user_dir, mods, ids, name)
    return f


def write_launcher_playset(game, user_dir, mods, ids, name=None):
    """Games that start with the active playset of their own list (EU5: <user dir>/playsets.json) ignore the load file.
    Put the chosen mods into the playset of that list with the playset's name (a new one when there is none) and make it
    the active one, so the app works as a front end for the game's own playsets. Everything else in the file (other
    playsets, keys we do not know) is kept, and flags are written the way the game writes them (only the active playset
    has `isActive`); the old file is saved as playsets.json.bak."""
    name = (name or LAUNCH_PLAYSET).strip() or LAUNCH_PLAYSET
    f = Path(user_dir) / game.playsets_file
    data = {}
    if f.is_file():
        try:
            data = json.loads(f.read_text(encoding="utf-8-sig"))
        except ValueError:
            data = {}
        if not isinstance(data, dict):
            data = {}
        shutil.copy2(f, f.with_suffix(".json.bak"))
    sets = data.get("playsets")
    if not isinstance(sets, list):
        sets = []
    sets = [p for p in sets if isinstance(p, dict)]
    live = [p for p in sets if not p.get("isRemoved")]
    same = [p for p in live if p.get("name") == name]
    mine = next((p for p in same if p.get("isActive")), same[0] if same else None)
    paths = [m.get("path") for p in sets for m in (p.get("orderedListMods") or []) if isinstance(m, dict) and isinstance(m.get("path"), str)]
    sep = "\\" if any("\\" in p for p in paths) else "/"
    trailing = bool(paths) and all(p.endswith(("/", "\\")) for p in paths)
    if mine is None:   # start from the playset in use so settings we do not know (DLC choice) carry over
        base = next((p for p in live if p.get("isActive")), None) or (live[0] if live else {})
        mine = {k: v for k, v in base.items() if k not in ("name", "isActive", "orderedListMods", "id", "isRemoved")}
        sets.append(mine)
    for p in sets:
        p.pop("isActive", None)
    mine["name"] = name
    mine["isActive"] = True
    mine.pop("isRemoved", None)
    mine["orderedListMods"] = [{"path": _launcher_path(game, user_dir, mods[mid], sep, trailing), "isEnabled": True} for mid in ids]
    data["playsets"] = sets
    _atomic_write(f, json.dumps(data, indent=2))
    return f


LAUNCH_PLAYSET = "Ronin Mod Manager"


def _launcher_path(game, user_dir, m, sep, trailing):
    """A mod's folder as the game's playset list writes it: the Workshop folder, or <user dir>/mod/<folder>."""
    p = m["root"] if m["source"] != "local" else str(Path(user_dir) / "mod" / Path(m["root"]).name)
    p = p.replace("\\", "/").rstrip("/")
    p = p.replace("/", sep)
    return p + sep if trailing else p
