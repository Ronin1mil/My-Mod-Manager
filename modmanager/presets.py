"""Curated playsets ("presets"): a named list of Workshop mods that can be turned into a playset in one click.

Presets are plain JSON. Built-in ones ship in modmanager/presets/, your own go in
<config>/<game>/presets/. A preset only names mods by Workshop id; applying it creates a normal playset
whose entries are `ws:<id>`, so anything not installed yet shows up as "not installed" until downloaded.
"""
import json
import re
from pathlib import Path

from .paths import config_dir

FORMAT = "modmanager-preset"
BUILTIN = Path(__file__).parent / "presets"
ID_RE = re.compile(r"^\d{1,20}$")
SAFE_ID = re.compile(r"^[a-z0-9][a-z0-9_.\-]{0,63}$")
MAX_MODS, MAX_FILE = 300, 256 * 1024
STATUSES = ("verified", "unverified")


def validate(doc, game_id=None):
    """Return a cleaned preset or raise ValueError. Everything is checked: presets are untrusted input."""
    if not isinstance(doc, dict) or doc.get("format") != FORMAT:
        raise ValueError("Not a preset file.")
    pid, game = doc.get("id"), doc.get("game")
    if not isinstance(pid, str) or not SAFE_ID.match(pid):
        raise ValueError("Preset needs an 'id' of lowercase letters, digits, - _ .")
    if not isinstance(game, str) or (game_id and game != game_id):
        raise ValueError(f"Preset is for '{game}', not '{game_id}'.")
    name = doc.get("name")
    if not isinstance(name, str) or not 0 < len(name.strip()) <= 60:
        raise ValueError("Preset needs a name of 1-60 characters.")
    mods = doc.get("mods")
    if not isinstance(mods, list) or not 0 < len(mods) <= MAX_MODS:
        raise ValueError(f"Preset needs 1-{MAX_MODS} mods.")
    clean, seen = [], set()
    for m in mods:
        if not isinstance(m, dict) or not isinstance(m.get("workshop_id"), (str, int)) \
                or not ID_RE.match(str(m["workshop_id"])):
            raise ValueError("Every preset mod needs a numeric 'workshop_id'.")
        wid = str(m["workshop_id"])
        if wid in seen:
            continue
        seen.add(wid)
        nm = m.get("name", wid)
        note = m.get("note", "")
        if not isinstance(nm, str) or not isinstance(note, str) or len(nm) > 120 or len(note) > 300:
            raise ValueError("Invalid mod name or note in preset.")
        clean.append({"workshop_id": wid, "name": nm, "note": note, "enabled": m.get("enabled", True) is not False})
    status = doc.get("status", "unverified")
    return {"id": pid, "game": game, "name": name.strip(), "description": str(doc.get("description", ""))[:1000],
            "source": str(doc.get("source", ""))[:300], "status": status if status in STATUSES else "unverified",
            "mods": clean}


def _load_dir(d, game_id, builtin):
    out = {}
    if not d.is_dir():
        return out
    for f in sorted(d.glob("*.json")):
        try:
            if f.stat().st_size > MAX_FILE:
                continue
            p = validate(json.loads(f.read_text(encoding="utf-8-sig")), game_id)
        except (OSError, ValueError):
            continue  # a broken preset file must never break the app
        p["builtin"] = builtin
        out[p["id"]] = p
    return out


def load_all(game):
    """{preset id: preset} for a game; your own presets override built-in ones with the same id."""
    out = _load_dir(BUILTIN, game.id, True)
    out.update(_load_dir(config_dir(game) / "presets", game.id, False))
    return out


def summarize(preset, mods):
    """Preset plus how many of its mods are installed right now."""
    have = {str(m["remote_id"]) for m in mods.values() if m.get("remote_id")}
    return {**preset, "installed": sum(1 for m in preset["mods"] if m["workshop_id"] in have),
            "total": len(preset["mods"])}


def to_playset_args(preset, mods):
    """(mod ids in preset order, disabled ids, missing [{workshop_id, name}])."""
    ids, off, missing = [], [], []
    have = {str(m["remote_id"]): m["id"] for m in mods.values() if m.get("remote_id")}
    for m in preset["mods"]:
        mid = have.get(m["workshop_id"]) or f"ws:{m['workshop_id']}"
        ids.append(mid)
        if m["workshop_id"] not in have:
            missing.append({"workshop_id": m["workshop_id"], "name": m["name"]})
        if not m["enabled"]:
            off.append(mid)
    return ids, off, missing


def save_user_preset(game, doc):
    """Validate and store a user preset (e.g. exported from a playset)."""
    p = validate(doc, game.id)
    d = config_dir(game) / "presets"
    d.mkdir(parents=True, exist_ok=True)
    (d / f"{p['id']}.json").write_text(json.dumps({**doc, "format": FORMAT}, indent=2), encoding="utf-8")
    return p


def from_playset(game, playset, mods, pid, name):
    """Turn a playset into a preset document (only Workshop mods can be shared this way)."""
    items = []
    for mid in playset["mods"]:
        m = mods.get(mid)
        rid = (m["remote_id"] if m else None) or (mid[3:] if mid.startswith("ws:") else None)
        if rid and ID_RE.match(str(rid)):
            items.append({"workshop_id": str(rid), "name": m["name"] if m else str(rid),
                          "enabled": mid not in playset["disabled"]})
    if not items:
        raise ValueError("This playset has no Workshop mods to put in a preset.")
    return {"format": FORMAT, "id": pid, "game": game.id, "name": name, "status": "unverified", "mods": items}
