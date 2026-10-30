"""Per-playset save folders.

Paradox games read saves from `<user dir>/save games`. To give each playset its own saves, that folder
is pointed at the playset's directory with a link (symlink; an NTFS junction on Windows, which
needs no admin rights). The game's own folder is never deleted or emptied: while a playset's folder is in use
it waits next to it as `save games (shared)` and is renamed back when a playset without its own saves starts.
"""
import json
import os
import re
import subprocess
import sys
from pathlib import Path

SAVES_DIR_NAME = "save games"
SHARED_SUFFIX = " (shared)"   # where the game's own saves wait while a playset's own folder is linked in


def shared_dir(game_saves):
    game_saves = Path(game_saves)
    return game_saves.parent / (game_saves.name + SHARED_SUFFIX)


def is_link(p):
    p = str(p)
    if os.path.islink(p):
        return True
    try:  # NTFS junctions: readlink works on them since Python 3.8
        os.readlink(p)
        return True
    except (OSError, ValueError):
        return False


def link_target(p):
    """Where a link points, as a normal path. Windows reports junction targets as '\\\\?\\C:\\...', which never
    compared equal to the app's own folders, so switching back to the game's saves silently did nothing there."""
    try:
        t = os.readlink(str(p))
    except (OSError, ValueError):
        return None
    if t.startswith("\\\\?\\UNC\\"):
        return "\\\\" + t[8:]
    if t.startswith(("\\\\?\\", "\\??\\")):
        return t[4:]
    return t


def _create_link(target, link):
    if sys.platform == "win32":
        r = subprocess.run(["cmd", "/c", "mklink", "/J", str(link), str(target)], capture_output=True)
        if r.returncode:
            raise OSError(r.stderr.decode(errors="replace").strip() or "mklink failed")
    else:
        os.symlink(str(target), str(link), target_is_directory=True)


def _remove_link(link):
    try:
        os.unlink(str(link))
    except OSError:
        os.rmdir(str(link))  # junctions are removed like empty directories; the target stays intact


def _same(a, b):
    return os.path.normcase(os.path.realpath(str(a))) == os.path.normcase(os.path.realpath(str(b)))


def _backup_name(game_saves):
    base = game_saves.parent / f"{game_saves.name} (original backup)"
    p, n = base, 2
    while os.path.lexists(str(p)):
        p = game_saves.parent / f"{base.name} {n}"
        n += 1
    return p


def activate(game_saves, profile_saves):
    """Make `game_saves` resolve to `profile_saves`. The game's own folder (when it is a real one) is renamed to
    `save games (shared)` first, never emptied. Returns 'already' | 'linked' | 'linked_after_moving:<path>' |
    'linked_after_backup:<path>' (only when a shared folder is already there, so neither is overwritten)."""
    game_saves, profile_saves = Path(game_saves), Path(profile_saves)
    profile_saves.mkdir(parents=True, exist_ok=True)
    game_saves.parent.mkdir(parents=True, exist_ok=True)
    if not os.path.lexists(str(game_saves)):
        _create_link(profile_saves, game_saves)
        return "linked"
    if is_link(game_saves):
        t = link_target(game_saves)
        if t and _same(t, profile_saves):
            return "already"
        _remove_link(game_saves)
        _create_link(profile_saves, game_saves)
        return "linked"
    if not game_saves.is_dir():
        raise ValueError(f"{game_saves} exists and is not a folder.")
    shared = shared_dir(game_saves)
    if not os.path.lexists(str(shared)):
        aside, note = shared, "linked_after_moving"
    else:
        try:
            game_saves.rmdir()  # an empty folder next to a kept shared one can simply be replaced
            _create_link(profile_saves, game_saves)
            return "linked"
        except OSError:
            aside, note = _backup_name(game_saves), "linked_after_backup"
    game_saves.rename(aside)
    try:
        _create_link(profile_saves, game_saves)
    except OSError:
        aside.rename(game_saves)  # undo: never leave the user without their saves
        raise
    return f"{note}:{aside}"


def deactivate(game_saves, managed_root):
    """Back to the game's normal, shared save folder: the link this app made (one pointing into `managed_root`) is
    removed and `save games (shared)` is renamed back. A real folder or someone else's link is left alone. Returns
    'unchanged' | 'restored' | 'unlinked:<folder the playset's saves stay in>'."""
    game_saves = Path(game_saves)
    shared = shared_dir(game_saves)
    if not os.path.lexists(str(game_saves)):
        if shared.is_dir() and not is_link(shared):  # interrupted earlier between the two steps below
            shared.rename(game_saves)
            return "restored"
        return "unchanged"
    if not is_link(game_saves):
        return "unchanged"
    target = link_target(game_saves)
    managed = os.path.normcase(os.path.realpath(str(managed_root)))
    if not target or not os.path.normcase(os.path.realpath(target)).startswith(managed + os.sep):
        return "unchanged"
    _remove_link(game_saves)
    if shared.is_dir() and not is_link(shared):
        shared.rename(game_saves)
    else:
        game_saves.mkdir()
    return f"unlinked:{target}"


# ---- which game version were these saves made with? ----
_HEADER_VERSION = re.compile(rb'(?:game_)?version\s*=\s*"?[^"\d\r\n]{0,40}?(\d+\.\d+(?:\.\d+){0,2})')
_PLAIN = re.compile(r"^(\d+)\.(\d+)")


def minor_of(version):
    """'1.14.2.1' -> '1.14' (patch releases do not break saves; a new minor release can)."""
    m = _PLAIN.match(str(version or "").strip())
    return f"{m.group(1)}.{m.group(2)}" if m else ""


def header_version(path, limit=16384):
    """Best effort: the version recorded in a save's readable header, '' when it is compressed/binary/unknown.
    Not verified against real saves of every game; the launch record below is the dependable source."""
    try:
        with open(path, "rb") as f:
            head = f.read(limit)
    except OSError:
        return ""
    m = _HEADER_VERSION.search(head)
    return m.group(1).decode() if m else ""


def latest_save(saves_dir):
    """Newest regular file in the folder (saves are single files for these games), or None."""
    best = None
    try:
        for e in os.scandir(str(saves_dir)):
            if e.is_file(follow_symlinks=False):
                t = e.stat().st_mtime
                if best is None or t > best[0]:
                    best = (t, Path(e.path))
    except OSError:
        return None
    return best[1] if best else None


def _record_path(cfg):
    return Path(cfg) / "save-versions.json"


def read_records(cfg):
    try:
        d = json.loads(_record_path(cfg).read_text(encoding="utf-8"))
        return d if isinstance(d, dict) else {}
    except (OSError, ValueError):
        return {}


def record_launch(cfg, key, version):
    """Remember which game version a save folder was last played with."""
    if not version:
        return
    d = read_records(cfg)
    d[key] = version
    p = _record_path(cfg)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(d, indent=2), encoding="utf-8")
    os.replace(tmp, p)


def saved_on(cfg, key, saves_dir):
    """(version, source) the saves in this folder were made with: newest save's header, else the last launch."""
    newest = latest_save(saves_dir)
    if newest:
        v = header_version(newest)
        if v:
            return v, "save"
    v = read_records(cfg).get(key, "")
    return (v, "launch") if v else ("", "")
