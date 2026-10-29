"""Read the playsets that already exist in a Paradox game's own launcher (launcher-v2.sqlite) so they can be imported.

The launcher keeps its data in a small SQLite file in the game's user folder:
  playsets(id, name, isActive, isRemoved, loadOrder, ...)
  playsets_mods(playsetId, modId, enabled, position)
  mods(id, displayName, name, steamId, pdxId, gameRegistryId, dirPath, source, ...)
(Table and column names as read by other mod managers; older launcher versions lack some columns, so every
column is optional here.)

The file is only ever READ, and only from a temporary copy: the launcher may have it open, and nothing here can
damage it or the launcher's playsets. Everything is best effort and never raises to the caller.
"""
import os
import re
import shutil
import sqlite3
import tempfile
from pathlib import Path

DB_NAMES = ("launcher-v2.sqlite", "launcher-v2_openbeta.sqlite")
MAX_PLAYSETS = 200
MAX_MODS = 2000


def db_files(user_dir):
    """The launcher database files present in the game's user folder, newest first."""
    if not user_dir:
        return []
    found = [Path(user_dir) / n for n in DB_NAMES]
    try:
        found = [p for p in found if p.is_file()]
        return sorted(found, key=lambda p: p.stat().st_mtime, reverse=True)
    except OSError:
        return []


def _columns(con, table):
    return {r[1] for r in con.execute(f'PRAGMA table_info("{table}")')}  # a missing table gives no rows; a damaged file raises


def _select(con, table, wanted):
    """Rows of `table` as dicts, asking only for the columns that exist."""
    have = _columns(con, table)
    cols = [c for c in wanted if c in have]
    if not cols:
        return []
    cur = con.execute(f'SELECT {", ".join(chr(34) + c + chr(34) for c in cols)} FROM "{table}"')
    return [dict(zip(cols, row)) for row in cur.fetchall()]


def _flag(v, default=False):
    if v is None:
        return default
    if isinstance(v, str):
        return v.strip().lower() in ("1", "true", "yes")
    return bool(v)


def _num(v, default=0):
    try:
        return int(float(v))
    except (TypeError, ValueError):
        return default


def read_playsets(db_file):
    """-> list of {id, name, active, mods: [{enabled, position, steam_id, pdx_id, registry_id, dir_path, name, source}]}
    in the launcher's order. Raises ValueError with a readable message if the file cannot be read."""
    tmp = tempfile.mkdtemp(prefix="modmanager-launcher-")
    try:
        copy = Path(tmp) / "launcher.sqlite"
        try:
            shutil.copyfile(db_file, copy)
            for ext in ("-wal", "-shm"):  # changes the launcher has not yet folded into the main file
                side = Path(str(db_file) + ext)
                if side.is_file():
                    shutil.copyfile(side, Path(str(copy) + ext))
        except OSError as e:
            raise ValueError(f"Could not read the launcher's database ({e.strerror or e}). Close the launcher and try again.")
        try:
            con = sqlite3.connect(f"file:{copy.as_posix()}?mode=ro", uri=True, timeout=5)
        except sqlite3.Error as e:
            raise ValueError(f"The launcher's database could not be opened ({e}).")
        try:
            con.text_factory = lambda b: b.decode("utf-8", "replace")
            ps_rows = _select(con, "playsets", ("id", "name", "isActive", "isRemoved", "loadOrder"))
            link_rows = _select(con, "playsets_mods", ("playsetId", "modId", "enabled", "position"))
            mod_rows = _select(con, "mods", ("id", "displayName", "name", "steamId", "pdxId", "gameRegistryId", "dirPath", "source"))
        except sqlite3.Error as e:
            raise ValueError(f"The launcher's database could not be read ({e}).")
        finally:
            con.close()
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    mods = {str(m.get("id")): m for m in mod_rows}
    by_playset = {}
    for l in link_rows:
        by_playset.setdefault(str(l.get("playsetId")), []).append(l)
    out = []
    for p in ps_rows[:MAX_PLAYSETS]:
        if _flag(p.get("isRemoved")):
            continue
        links = sorted(by_playset.get(str(p.get("id")), []), key=lambda l: _num(l.get("position")))[:MAX_MODS]
        items = []
        for l in links:
            m = mods.get(str(l.get("modId")), {})
            items.append({"enabled": _flag(l.get("enabled"), True), "position": _num(l.get("position")),
                          "steam_id": str(m.get("steamId") or ""), "pdx_id": str(m.get("pdxId") or ""),
                          "registry_id": str(m.get("gameRegistryId") or ""), "dir_path": str(m.get("dirPath") or ""),
                          "name": str(m.get("displayName") or m.get("name") or ""), "source": str(m.get("source") or "")})
        out.append({"id": str(p.get("id")), "name": str(p.get("name") or "Launcher playset")[:100],
                    "active": _flag(p.get("isActive")), "mods": items})
    return out


def match_mod(item, mods):
    """The app's id for one launcher mod, or None. `mods` is the app's scanned {id: info}. Tried in order:
    Workshop id, the launcher's descriptor name (mod/ugc_123.mod or mod/name.mod), the folder, the display name."""
    sid = item.get("steam_id", "")
    if sid.isdigit() and f"ws:{sid}" in mods:
        return f"ws:{sid}"
    reg = item.get("registry_id", "").replace("\\", "/")
    m = re.fullmatch(r"(?:mod/)?ugc_(\d+)\.mod", reg)
    if m and f"ws:{m.group(1)}" in mods:
        return f"ws:{m.group(1)}"
    m = re.fullmatch(r"(?:mod/)?(.+)\.mod", reg)
    if m and f"local:{m.group(1)}" in mods:
        return f"local:{m.group(1)}"
    d = os.path.normcase(os.path.normpath(item.get("dir_path", ""))) if item.get("dir_path") else ""
    if d:
        for mid, info in mods.items():
            if info.get("root") and os.path.normcase(os.path.normpath(info["root"])) == d:
                return mid
    nm = item.get("name", "")
    if nm:
        same = [mid for mid, info in mods.items() if info.get("name") == nm]
        if len(same) == 1:
            return same[0]
    return None


def convert(playset, mods):
    """-> (ordered mod ids, disabled ids, [names that could not be matched and have no Workshop id]).
    A mod that is not installed but has a Workshop id is kept as 'ws:<id>' so the playset shows it as not
    installed (and the Presets / Warnings flow can fetch it) instead of dropping it."""
    order, off, lost = [], [], []
    for it in playset["mods"]:
        mid = match_mod(it, mods)
        if mid is None and it.get("steam_id", "").isdigit():
            mid = f"ws:{it['steam_id']}"
        if mid is None:
            lost.append(it.get("name") or it.get("pdx_id") or it.get("registry_id") or "?")
            continue
        if mid in order:
            continue
        order.append(mid)
        if not it.get("enabled", True):
            off.append(mid)
    return order, off, lost
