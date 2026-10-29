"""Playset persistence (JSON), sharing, and export to the game's load file (dlc_load.json / content_load.json)."""
import json
import shutil
import time
import uuid
from pathlib import Path

from .launch import validate_launch_args
from .paths import config_dir

SHARE_FORMAT = "modmanager-playset"
LEGACY_SHARE = {"vic3mm-playset": "vic3", "eu5mm-playset/1": "eu5"}  # files from the standalone managers

MAX_NAME, MAX_NOTES, MAX_MODS = 60, 2000, 5000
DEFAULTS = {"notes": "", "launch_args": [], "auto_sort": True, "separate_saves": False}


# per-game settings (folders + base-game comparison); app-wide ones live in GlobalSettings
SETTINGS_DEFAULTS = {"game_dir": "", "user_dir": "", "workshop_dir": "", "include_vanilla": True,
                     "setup_done": False, "steamcmd": "", "steam_user": "", "save_version_check": True}
GLOBAL_DEFAULTS = {"auto_update_check": False, "dismissed_update": "", "last_game": ""}


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
    tmp.write_text(text)
    tmp.replace(path)


class Store:
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
        elif game is not None:
            self.import_legacy(game)

    def import_legacy(self, game):
        """First start of a game: adopt playsets from the standalone manager it replaces (copy, never move)."""
        from .paths import legacy_config_files
        for f in legacy_config_files(game):
            try:
                d = json.loads(f.read_text(encoding="utf-8-sig"))
            except (OSError, ValueError):
                continue
            if isinstance(d, dict) and isinstance(d.get("playsets"), dict):
                keep = {k: d["playsets"][k] for k, v in d["playsets"].items() if isinstance(v, dict)
                        and isinstance(v.get("mods", []), list)}
                for k, v in keep.items():
                    v.setdefault("id", k)
                    v.setdefault("name", "Imported")
                    v.setdefault("mods", [])
                    v.setdefault("disabled", [])
                    v.setdefault("created", int(time.time()))
                self.data["playsets"] = keep
                self.data["active"] = d.get("active") if d.get("active") in keep else next(iter(keep), None)
                self.data["imported_from"] = str(f)
                self.save()
                return True
        return False

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
              "disabled": _id_list(disabled or [], "disabled"), "created": int(time.time()), **_defaults()}
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

    def get(self, pid):
        ps = self.data["playsets"][pid]
        for k, v in _defaults().items():
            ps.setdefault(k, v)
        return ps

    def update(self, pid, **fields):
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
        for k in ("auto_sort", "separate_saves"):
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
        self.data["playsets"].pop(pid, None)
        if self.data["active"] == pid:
            self.data["active"] = next(iter(self.data["playsets"]), None)
        self.save()

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
            raise ValueError("Not a Mod Manager playset file")
        fmt = data.get("format")
        legacy_game = LEGACY_SHARE.get(fmt)
        if fmt != SHARE_FORMAT and legacy_game is None:
            raise ValueError("Not a Mod Manager playset file")
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
            d = json.loads(self.path.read_text())
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
    mod folder (local) or its Workshop folder."""
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


def write_load_file(game, user_dir, mods, ids):
    """Write the game's load file (what it reads at startup), backing up the previous one."""
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
    cur["enabled_mods"] = [mod_entry(game, mods[mid]) for mid in ids]
    cur.setdefault("disabled_dlcs", [])
    _atomic_write(f, json.dumps(cur, indent=2))
    return f
