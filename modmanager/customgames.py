"""Games the user adds in the app (beta).

The engine never mentions a specific game, so a game is only data (see games.Game). This module turns a small form
into that data: it checks every field (folder names may not climb out of their folder), builds the Game, and keeps the
list in `custom_games.json` next to the settings. Nothing here is verified against a real install of any game: the
templates are best knowledge, and the app says so.
"""
import json
import re

from .games import Game
from .paths import config_dir
from .store import _atomic_write

MAX_GAMES = 20
FORMAT = "modmanager-custom-games"

_PART = re.compile(r"^[\w][\w .&'()+\-]{0,63}$")        # one folder or file name, no slashes
_FILE = re.compile(r"^[\w][\w .\-]{0,63}$")
_HEX = re.compile(r"^#[0-9a-fA-F]{6}$")
_ID = re.compile(r"^[A-Za-z0-9_.\-]{1,64}$")
KINDS = ("paradox", "modules")
STYLES = ("descriptor", "path")

# What the form starts from. All of it is from memory of other mod managers, not checked on a real install.
TEMPLATES = [
    {"key": "paradox", "label": "Blank Paradox game", "kind": "paradox", "user_parent": "Paradox Interactive",
     "load_file": "dlc_load.json", "load_style": "descriptor", "content_dir": "game", "install_marker": "game/common",
     "def_dirs": "common, events", "vanilla_only": ""},
    {"key": "stellaris", "label": "Stellaris (unverified)", "kind": "paradox", "name": "Stellaris", "app_id": "281990",
     "user_parent": "Paradox Interactive", "user_dir_name": "Stellaris", "install_dir_name": "Stellaris",
     "load_file": "dlc_load.json", "load_style": "descriptor", "content_dir": "", "install_marker": "common",
     "def_dirs": "common, events, map, localisation", "vanilla_only": "common, events, map, localisation"},
    {"key": "imperator", "label": "Imperator: Rome (unverified)", "kind": "paradox", "name": "Imperator: Rome",
     "app_id": "859580", "user_parent": "Paradox Interactive", "user_dir_name": "Imperator",
     "install_dir_name": "ImperatorRome", "load_file": "dlc_load.json", "load_style": "descriptor",
     "content_dir": "game", "install_marker": "game/common", "def_dirs": "common, events", "vanilla_only": ""},
    {"key": "modules", "label": "Blank Bannerlord-style game (modules)", "kind": "modules", "user_parent": "",
     "content_dir": "Modules", "install_marker": "Modules/Native", "load_style": "descriptor", "load_file": "(command line)",
     "def_dirs": "", "vanilla_only": "", "seed_mods": "Native", "exe_rel": "bin/Win64_Shipping_Client/Game.exe",
     "launch_prefix": ""},
]


def _text(d, key, default="", limit=80):
    v = d.get(key, default)
    if v is None:
        v = default
    if not isinstance(v, str):
        raise ValueError(f"'{key}' must be text.")
    v = v.strip()
    if len(v) > limit:
        raise ValueError(f"'{key}' is too long.")
    return v


def _parts(v, what, allow_empty=False):
    """'game/common' or ['game','common'] -> ('game','common'). Every part is a plain name: no '..', no drive, no slashes."""
    if isinstance(v, str):
        v = [p for p in re.split(r"[\\/]+", v.strip()) if p]
    if not isinstance(v, (list, tuple)) or not all(isinstance(p, str) for p in v):
        raise ValueError(f"'{what}' must be a folder path like game/common.")
    v = [p.strip() for p in v if p.strip()]
    if (not v and not allow_empty) or len(v) > 6:
        raise ValueError(f"'{what}' must be a folder path like game/common (1 to 6 folders).")
    for p in v:
        if p in (".", "..") or not _PART.match(p):
            raise ValueError(f"'{what}': '{p}' is not a plain folder name.")
    return tuple(v)


def _names(v, what, pattern=_FILE, limit=30):
    if isinstance(v, str):
        v = [p.strip() for p in re.split(r"[,\n;]+", v) if p.strip()]
    if not isinstance(v, (list, tuple)) or not all(isinstance(p, str) for p in v) or len(v) > limit:
        raise ValueError(f"'{what}' must be a comma separated list of names.")
    for p in v:
        if not pattern.match(p):
            raise ValueError(f"'{what}': '{p}' is not a plain name.")
    return tuple(dict.fromkeys(v))


def clean(d):
    """Check one definition from the form and return it normalised (the exact shape that is stored)."""
    if not isinstance(d, dict):
        raise ValueError("Invalid game definition.")
    name = _text(d, "name", limit=40)
    if not name or not re.search(r"[\w]", name):
        raise ValueError("Give the game a name.")
    kind = _text(d, "kind", "paradox")
    if kind not in KINDS:
        raise ValueError("The game type must be 'paradox' or 'modules'.")
    app_id = _text(d, "app_id", limit=12)
    if app_id and not app_id.isdigit():
        raise ValueError("The Steam app id is a number (find it in the game's Steam store address).")
    user_dir_name = _text(d, "user_dir_name") or re.sub(r"[^\w .\-]", "", name).strip()
    if not _PART.match(user_dir_name):
        raise ValueError("'user_dir_name' is not a plain folder name.")
    parent = _text(d, "user_parent", "Paradox Interactive" if kind == "paradox" else "")
    if parent and not _PART.match(parent):
        raise ValueError("'user_parent' is not a plain folder name.")
    install = _text(d, "install_dir_name") or user_dir_name
    if not _PART.match(install):
        raise ValueError("'install_dir_name' is not a plain folder name.")
    marker = _parts(d.get("install_marker") or ("game/common" if kind == "paradox" else "Modules/Native"), "install_marker")
    content = _parts(d.get("content_dir", "game" if kind == "paradox" else "Modules"), "content_dir", allow_empty=True)
    style = _text(d, "load_style", "descriptor")
    if style not in STYLES:
        raise ValueError("The load style must be 'descriptor' or 'path'.")
    load_file = _text(d, "load_file", "dlc_load.json" if kind == "paradox" else "(command line)", limit=64)
    if kind == "paradox" and not _FILE.match(load_file):
        raise ValueError("'load_file' is a file name like dlc_load.json.")
    accent = _text(d, "accent", "#8fa8d0", limit=7)
    if not _HEX.match(accent):
        raise ValueError("The accent colour must look like #8fa8d0.")
    out = {"name": name, "kind": kind, "app_id": app_id, "user_parent": parent, "user_dir_name": user_dir_name,
           "install_dir_name": install, "install_marker": "/".join(marker), "content_dir": "/".join(content),
           "load_file": load_file, "load_style": style, "accent": accent.lower(),
           "def_dirs": ", ".join(_names(d.get("def_dirs", "common, events" if kind == "paradox" else ""), "def_dirs")),
           "vanilla_only": ", ".join(_names(d.get("vanilla_only", ""), "vanilla_only"))}
    if kind == "modules":
        out["seed_mods"] = ", ".join(_names(d.get("seed_mods", ""), "seed_mods", re.compile(r"^[A-Za-z0-9_.\-]{1,64}$")))
        out["exe_rel"] = "/".join(_parts(d.get("exe_rel") or "bin/Win64_Shipping_Client/Game.exe", "exe_rel"))
        lp = d.get("launch_prefix", "")
        lp = re.sub(r"\s+", ",", lp.strip()) if isinstance(lp, str) else lp
        out["launch_prefix"] = " ".join(_names(lp, "launch_prefix", re.compile(r"^[-/][A-Za-z0-9_.:=\-]{1,40}$"), 6))
    return out


def _mix(a, b, t):
    """Blend colour a toward colour b by t (0..1); both '#rrggbb'."""
    ca = [int(a[i:i + 2], 16) for i in (1, 3, 5)]
    cb = [int(b[i:i + 2], 16) for i in (1, 3, 5)]
    return "#" + "".join(f"{round(x * (1 - t) + y * t):02x}" for x, y in zip(ca, cb))


def theme_from(accent):
    """A dark theme in the chosen accent colour (the built-in games have hand-made ones)."""
    lum = sum(int(accent[i:i + 2], 16) * w for i, w in ((1, .299), (3, .587), (5, .114)))
    return {"--ink": "#ece8e2", "--mut": _mix("#9a9a9a", accent, .15), "--bg": _mix("#0c0c0e", accent, .06),
            "--side": _mix("#0a0a0c", accent, .05), "--panel": _mix("#141416", accent, .08), "--line": _mix("#26262a", accent, .18),
            "--acc": accent, "--accink": "#14141a" if lum > 140 else "#ffffff", "--p1": _mix(accent, "#000000", .55),
            "--p2": _mix(accent, "#000000", .4), "--p3": _mix(accent, "#000000", .65)}


def to_game(gid, d):
    """Build the Game from a cleaned definition."""
    kind = d["kind"]
    content = d["content_dir"]
    marker = tuple(d["install_marker"].split("/"))
    names = lambda v: tuple(x.strip() for x in v.split(",") if x.strip())
    extra = {}
    if kind == "modules":
        extra = {"seed_mods": names(d.get("seed_mods", "")), "exe_rel": tuple(d["exe_rel"].split("/")),
                 "launch_prefix": tuple(d.get("launch_prefix", "").split())}
    return Game(id=gid, name=d["name"], app_id=d["app_id"] or "0", user_dir_name=d["user_dir_name"],
                install_dir_name=d["install_dir_name"], install_marker=marker, load_file=d["load_file"],
                load_style=d["load_style"], def_dirs=names(d["def_dirs"]), vanilla_only=names(d["vanilla_only"]),
                theme=theme_from(d["accent"]), verified=False, kind=kind, user_parent=d["user_parent"],
                content_dir=content, custom=True, **extra)


class CustomGames:
    """The saved list. `path=None` keeps it in memory only (tests, a Hub built around given games)."""

    def __init__(self, path=None):
        self.path = path
        self.defs = {}   # id -> cleaned definition, in the order added
        if path is None:
            return
        try:
            doc = json.loads(path.read_text(encoding="utf-8-sig"))
            items = doc.get("games") if isinstance(doc, dict) else None
            for it in items if isinstance(items, list) else []:
                try:   # one bad entry must not hide the others
                    gid = it.get("id")
                    if isinstance(gid, str) and _ID.match(gid) and gid.startswith("cg-") and gid not in self.defs:
                        self.defs[gid] = clean(it)
                except (ValueError, AttributeError):
                    continue
        except (OSError, ValueError):
            pass

    @classmethod
    def default(cls):
        return cls(config_dir() / "custom_games.json")

    def games(self):
        return [to_game(i, d) for i, d in self.defs.items()]

    def _save(self):
        if self.path is not None:
            _atomic_write(self.path, json.dumps({"format": FORMAT, "games": [{"id": i, **d} for i, d in self.defs.items()]}, indent=2))

    def new_id(self, name, taken):
        base = "cg-" + (re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")[:24] or "game")
        gid, n = base, 2
        while gid in self.defs or gid in taken:
            gid, n = f"{base}-{n}", n + 1
        return gid

    def save(self, d, gid=None, taken=()):
        """Add (gid None) or replace a game -> (id, Game)."""
        c = clean(d)
        if gid is None:
            if len(self.defs) >= MAX_GAMES:
                raise ValueError(f"At most {MAX_GAMES} added games.")
            gid = self.new_id(c["name"], taken)
        elif gid not in self.defs:
            raise KeyError(gid)
        self.defs[gid] = c
        self._save()
        return gid, to_game(gid, c)

    def remove(self, gid):
        if gid not in self.defs:
            raise KeyError(gid)
        del self.defs[gid]
        self._save()

    def clear(self):
        self.defs = {}
        if self.path is not None:
            try:
                self.path.unlink()
            except OSError:
                pass
