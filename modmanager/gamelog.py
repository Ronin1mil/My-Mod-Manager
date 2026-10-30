"""One log per game of what the app did with it: what it found at start, and, for every Play, which mods it handed to
the game, which files it wrote, what those files looked like before and after, and (a little later) whether the game
or its launcher changed them again. Meant to be sent in as one file when a game does not start the way the app said.

<Documents>/Ronin Mod Manager/RoninModManager-<game id>.log, next to the error log (~1 MB, one rotated copy). Always on.
Never raises. Records mod names, ids and folders, not mod contents; the Windows user name is replaced by <user>.
"""
import json
import os
import re
import threading
import time
from pathlib import Path

from . import APP_NAME, BUILD, __version__, errorlog

MAX_BYTES = 1024 * 1024
FOLLOW_UP = (15, 90)   # seconds after Play at which the game's files are looked at again
_lock = threading.Lock()


def log_path(game_id):
    return errorlog.log_path().parent / f"RoninModManager-{game_id}.log"


def _names():
    out = {Path.home().name, os.environ.get("USERNAME", ""), os.environ.get("USER", "")}
    return sorted((n for n in out if len(n) >= 3 and n.lower() not in ("root", "user", "admin")), key=len, reverse=True)


def redact(text):
    for n in _names():
        text = re.sub(re.escape(n), "<user>", text, flags=re.I)
    return text


def log(game_id, message, lines=()):
    """Append a timestamped entry; `lines` are indented under it."""
    try:
        body = f"{time.strftime('%Y-%m-%d %H:%M:%S')}  {message}\n" + "".join(f"    {l}\n" for l in lines)
        body = redact(body)
        p = log_path(game_id)
        with _lock:
            p.parent.mkdir(parents=True, exist_ok=True)
            new = not p.exists()
            if not new and p.stat().st_size > MAX_BYTES:
                os.replace(p, p.with_name(p.name + ".1"))
                new = True
            with open(p, "a", encoding="utf-8", errors="replace") as f:
                if new:
                    f.write(f"{APP_NAME} {__version__}{' build ' + BUILD if BUILD else ''} - what the app did with '{game_id}'\n\n")
                f.write(body)
    except Exception:
        pass


def _json(path):
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8-sig"))
        return data if isinstance(data, dict) else None
    except (OSError, ValueError):
        return None


def snapshot(game, user_dir):
    """What the game's own files say right now: its playset list (which playset is active and its mods) and its load file.
    Never raises: a folder that cannot be read is a line in the log."""
    try:
        return _snapshot(game, user_dir)
    except Exception as e:
        return [f"(could not look at the game's files: {type(e).__name__}: {e})"]


def _snapshot(game, user_dir):
    out = []
    if not user_dir:
        return ["(no user folder)"]
    d = Path(user_dir)
    for name in filter(None, (game.playsets_file, game.load_file)):
        f = d / name
        if not f.is_file():
            out.append(f"{name}: not there")
            continue
        when = time.strftime("%H:%M:%S", time.localtime(f.stat().st_mtime))
        data = _json(f)
        if data is None:
            out.append(f"{name}: written {when}, could not be read as JSON")
        elif name == game.playsets_file:
            sets = [p for p in data.get("playsets") or [] if isinstance(p, dict)]
            out.append(f"{name}: written {when}, {len(sets)} playsets")
            for p in sets:
                mods = [m for m in p.get("orderedListMods") or [] if isinstance(m, dict)]
                on = sum(1 for m in mods if m.get("isEnabled", True))
                flags = " ".join(k for k in ("isActive", "isRemoved") if p.get(k))
                out.append(f"  - {p.get('name')!r}: {on}/{len(mods)} mods enabled{'  [' + flags + ']' if flags else ''}")
            for p in sets:
                if p.get("isActive"):
                    out.append(f"  active playset {p.get('name')!r}, in order:")
                    out += [f"    {'+' if m.get('isEnabled', True) else '-'} {m.get('path')}" for m in p.get("orderedListMods") or [] if isinstance(m, dict)]
        else:
            mods = data.get("enabled_mods")
            out.append(f"{name}: written {when}, {len(mods) if isinstance(mods, list) else '?'} mods enabled")
    out += recent_files(d)
    return out


SKIP_DIRS = {"mod", "save games", "saves", "logs", "crashes", "cache", "screenshots", "pops", "dumps"}


def recent_files(d, minutes=15, limit=25):
    """Files the game (or anything else) changed in its user folder lately, top level and one folder down (mods, saves
    and logs are skipped): this is how a file that decides which playset starts shows up."""
    cutoff = time.time() - minutes * 60
    found = []
    try:
        for e in os.scandir(d):
            if e.is_file():
                found.append((e.stat().st_mtime, e.name, e.stat().st_size))
            elif e.is_dir() and e.name.lower() not in SKIP_DIRS:
                for f in os.scandir(e.path):
                    if f.is_file():
                        found.append((f.stat().st_mtime, f"{e.name}/{f.name}", f.stat().st_size))
    except OSError as err:
        return [f"(could not list the folder: {err})"]
    new = sorted((t, n, z) for t, n, z in found if t >= cutoff)[-limit:]
    return [f"changed in the last {minutes} min in the user folder:"] + (
        [f"  {time.strftime('%H:%M:%S', time.localtime(t))}  {z:>8} bytes  {n}" for t, n, z in new] or ["  (nothing)"])


def raw_text(game, user_dir, limit=60000):
    """The game's playset list exactly as it is on disk, for the follow-up entries."""
    try:
        text = (Path(user_dir) / game.playsets_file).read_text(encoding="utf-8-sig", errors="replace")
    except OSError as e:
        return [f"(could not read {game.playsets_file}: {e})"]
    return [f"{game.playsets_file} as it is on disk ({len(text)} characters):"] + [("  " + l)[:300] for l in text[:limit].splitlines()]


def follow_up(game, user_dir, delays=FOLLOW_UP):
    """Look at the game's files again after Play: if the game or its launcher put its own playset back, it shows here."""
    if os.environ.get("MODMANAGER_FOLLOW_UP") == "0":
        return

    def look(secs):
        log(game.id, f"{secs} s after Play: the game's files now say",
            snapshot(game, user_dir) + (raw_text(game, user_dir) if game.playsets_file else []))

    for secs in delays:
        t = threading.Timer(secs, look, args=(secs,))
        t.daemon = True
        t.start()
