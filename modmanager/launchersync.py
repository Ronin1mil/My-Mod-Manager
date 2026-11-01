"""Keep the game's own playset in step with the app's active playset (Crusader Kings III first).

Starting CK3 from Steam opens the Paradox launcher, which writes ITS active playset into dlc_load.json before the game
starts, so a change made only in this app was lost. After every change to the active playset the app therefore also
writes it into the launcher's database (launcher-v2.sqlite in the game's user folder): a launcher playset with the same
name gets the same mods in the same order and on/off state, and becomes the launcher's active playset.

Rules: never while the launcher is running (it keeps its own copy and would write it back); the database is backed up
once a day before the first change; only mods the launcher already knows are listed (it learns new ones itself the next
time it starts), and those it does not know are reported.
"""
import os
import shutil
import subprocess
import sys
import time
import uuid
from pathlib import Path

from . import launcherdb

LAUNCHER_PROCESSES = ("dowser.exe", "paradox launcher.exe")


def launcher_running():
    if sys.platform != "win32":
        return False
    try:
        r = subprocess.run(["tasklist", "/NH", "/FO", "CSV"], capture_output=True, text=True, timeout=15,
                           creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    except (OSError, subprocess.SubprocessError):
        return False
    names = {line.split('","')[0].strip('"').lower() for line in r.stdout.splitlines() if line}
    return any(p in names for p in LAUNCHER_PROCESSES)


def _norm(p):
    return os.path.normcase(os.path.normpath(str(p))) if p else ""


def _backup(db):
    """One copy per day, next to it: launcher-v2.sqlite.ronin-backup-<date>."""
    b = db.with_name(f"{db.name}.ronin-backup-{time.strftime('%Y%m%d')}")
    if not b.exists():
        shutil.copy2(db, b)
    return b


def sync(user_dir, name, enabled, disabled, mods, registry_id, running=None):
    """Write a playset into the launcher's database under `name` and make it the active one: `enabled` mod ids in load
    order (as the game will load them), then `disabled` ones switched off. `registry_id(mod)` gives a mod's
    'mod/<name>.mod' path. -> {status: synced|launcher_open|no_db, file, missing, created}"""
    dbs = launcherdb.db_files(user_dir)
    if not dbs:
        return {"status": "no_db", "file": "", "missing": [], "created": False}
    db = dbs[0]
    if (running or launcher_running)():
        return {"status": "launcher_open", "file": str(db), "missing": [], "created": False}
    sqlite3 = launcherdb._sqlite()
    _backup(db)
    con = sqlite3.connect(str(db), timeout=5)
    try:
        con.execute("BEGIN IMMEDIATE")
        rows = con.execute('SELECT id, steamId, gameRegistryId, dirPath FROM mods').fetchall()
        by_steam = {str(s): i for i, s, _, _ in rows if s}
        by_reg = {g: i for i, _, g, _ in rows if g}
        by_dir = {_norm(d): i for i, _, _, d in rows if d}
        order, missing = [], []
        for mid, on in [*((i, True) for i in enabled), *((i, False) for i in disabled if i not in enabled)]:
            m = mods.get(mid)
            if not m:
                continue
            lid = (by_dir.get(_norm(m.get("root"))) or (by_steam.get(str(m["remote_id"])) if m.get("remote_id") else None)
                   or by_reg.get(registry_id(m)))
            if lid and all(lid != x for x, _ in order):
                order.append((lid, on))
            else:
                missing.append(m.get("name") or mid)
        now = int(time.time() * 1000)   # the launcher stores times as milliseconds
        found = con.execute("SELECT id FROM playsets WHERE name = ? AND isRemoved = 0 ORDER BY isActive DESC LIMIT 1",
                            (name,)).fetchone()
        created = not found
        if found:
            pid = found[0]
            con.execute("UPDATE playsets SET updatedOn = ?, lastUsedAt = ? WHERE id = ?", (now, now, pid))
        else:
            pid = str(uuid.uuid4())
            con.execute("INSERT INTO playsets (id, name, isActive, loadOrder, createdOn, updatedOn, isRemoved, hasNotApprovedChanges,"
                        " syncState, state, owned, author, subscribersCount, ratingsCount, offDisk, lastUsedAt)"
                        " VALUES (?, ?, 0, 'custom', ?, ?, 0, 0, 'NOT_ELIGIBLE', 'private', 1, '', 0, 0, 0, ?)",
                        (pid, name, now, now, now))
        con.execute("DELETE FROM playsets_mods WHERE playsetId = ?", (pid,))
        con.executemany("INSERT INTO playsets_mods (playsetId, modId, enabled, position) VALUES (?, ?, ?, ?)",
                        [(pid, lid, 1 if on else 0, n) for n, (lid, on) in enumerate(order)])
        con.execute("UPDATE playsets SET isActive = CASE WHEN id = ? THEN 1 ELSE 0 END", (pid,))
        con.commit()
    except Exception:
        con.rollback()
        raise
    finally:
        con.close()
    return {"status": "synced", "file": str(db), "missing": missing, "created": created}
