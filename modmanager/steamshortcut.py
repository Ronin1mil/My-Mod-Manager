"""Add the app to Steam as a non-Steam game, so it can be started from the Steam library.

Steam keeps non-Steam games in `<Steam>/userdata/<account id>/config/shortcuts.vdf`, a small binary key/value file.
It is read and written back exactly (anything the app does not know about is kept), with one entry for this app added,
or updated when it is already there. Steam rewrites that file when it exits, so it is only changed while Steam is
closed, and the old file is backed up first.
"""
import os
import re
import subprocess
import sys
import time
import zlib
from pathlib import Path

from . import shortcut

APP_NAME = "Ronin Mod Manager"
_MAP, _STR, _INT, _END = 0, 1, 2, 8


# ---- the binary format: maps of strings, 32-bit ints and maps, as an ordered list of (key, value) ----
def parse(data):
    """bytes -> [(key, value)], value = str | int | [(key, value)]. Raises ValueError on anything it does not know."""
    pos = 0

    def cstr():
        nonlocal pos
        end = data.index(b"\x00", pos)
        s = data[pos:end].decode("utf-8", "surrogateescape")
        pos = end + 1
        return s

    def block():
        nonlocal pos
        out = []
        while True:
            if pos >= len(data):
                raise ValueError("shortcuts.vdf ends in the middle of a block")
            t = data[pos]
            pos += 1
            if t == _END:
                return out
            key = cstr()
            if t == _MAP:
                out.append((key, block()))
            elif t == _STR:
                out.append((key, cstr()))
            elif t == _INT:
                out.append((key, int.from_bytes(data[pos:pos + 4], "little", signed=True)))
                pos += 4
            else:
                raise ValueError(f"unknown field type {t} in shortcuts.vdf")
    try:
        root = block()
    except IndexError:
        raise ValueError("shortcuts.vdf is cut off")
    if pos != len(data) and data[pos:] not in (b"\x08", b""):
        raise ValueError("shortcuts.vdf has data after its end")
    return root


def dump(items):
    out = bytearray()
    for key, v in items:
        k = key.encode("utf-8", "surrogateescape") + b"\x00"
        if isinstance(v, list):
            out += bytes([_MAP]) + k + dump(v) + bytes([_END])
        elif isinstance(v, bool) or not isinstance(v, (int, str)):
            raise TypeError(f"cannot store {type(v).__name__} in shortcuts.vdf")
        elif isinstance(v, int):
            out += bytes([_INT]) + k + (v & 0xFFFFFFFF).to_bytes(4, "little")
        else:
            out += bytes([_STR]) + k + v.encode("utf-8", "surrogateescape") + b"\x00"
    return bytes(out)


def dumps(root):
    """The whole file: Steam writes one more end marker after the outer block."""
    return dump(root) + bytes([_END])


# ---- where Steam keeps it ----
def steam_root():
    from .paths import registry_steam_roots, steam_roots
    for r in [*registry_steam_roots(), *steam_roots()]:
        if (Path(r) / "userdata").is_dir():
            return Path(r)
    return None


def _most_recent_account(root):
    """The account id (the userdata folder name) of the Steam user who logged in last, from config/loginusers.vdf."""
    try:
        text = (Path(root) / "config" / "loginusers.vdf").read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    users = re.findall(r'"(\d{17})"\s*\{([^{}]*)\}', text)

    def rank(u):   # newer Steam has no MostRecent: the auto-login account, then the latest login
        body = u[1]
        stamp = re.search(r'"timestamp"\s*"(\d+)"', body)
        return (bool(re.search(r'"MostRecent"\s*"1"', body)), bool(re.search(r'"AutoLogin"\s*"1"', body)), int(stamp.group(1)) if stamp else 0)
    if not users:
        return None
    return str(int(max(users, key=rank)[0]) - 76561197960265728)


def shortcuts_file(root=None):
    """The shortcuts.vdf of the Steam user who logged in last (or the only one there is)."""
    root = Path(root) if root else steam_root()
    if not root:
        raise ValueError("Steam was not found on this PC.")
    users = [d for d in (root / "userdata").iterdir() if d.is_dir() and d.name.isdigit()] if (root / "userdata").is_dir() else []
    want = _most_recent_account(root)
    pick = next((d for d in users if d.name == want), None)
    if not pick:
        with_config = [d for d in users if (d / "config").is_dir()]
        if len(with_config) != 1:
            raise ValueError("Could not tell which Steam account to add it to. Log in to Steam once, close it, and try again.")
        pick = with_config[0]
    return pick / "config" / "shortcuts.vdf"


def status():
    """For the Settings page: is Steam here, and is this app already in its library?"""
    try:
        f = shortcuts_file()
    except (ValueError, OSError):
        return {"available": False, "added": False}
    try:
        added = f.is_file() and any(isinstance(g, list) and dict(g).get("AppName") == APP_NAME for _, g in parse(f.read_bytes())[0][1])
    except (ValueError, OSError, IndexError):
        added = False
    return {"available": True, "added": added}


def steam_running():
    if sys.platform != "win32":
        return False
    try:
        r = subprocess.run(["tasklist", "/FI", "IMAGENAME eq steam.exe", "/NH"], capture_output=True, text=True, timeout=15,
                           creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    except (OSError, subprocess.SubprocessError):
        return False
    return "steam.exe" in r.stdout.lower()


# ---- our entry ----
def app_id(exe, name, taken=()):
    """An id for the entry: crc32 of the quoted exe and the name with the top bit set (what tools that add non-Steam
    games use; Steam itself keeps whatever id the file has), moved on if another entry already has it. Unsigned."""
    n = zlib.crc32((exe + name).encode("utf-8")) | 0x80000000
    while n in taken:
        n = ((n + 1) & 0x7FFFFFFF) | 0x80000000
    return n


def entry(exe, args, folder, icon, name=APP_NAME, taken=()):
    q = f'"{exe}"'
    return [("appid", app_id(q, name, taken) - (1 << 32)), ("AppName", name), ("Exe", q), ("StartDir", f'"{folder}"'),
            ("icon", icon), ("ShortcutPath", ""), ("LaunchOptions", args), ("IsHidden", 0), ("AllowDesktopConfig", 1),
            ("AllowOverlay", 1), ("OpenVR", 0), ("Devkit", 0), ("DevkitGameID", ""), ("DevkitOverrideAppID", 0),
            ("LastPlayTime", 0), ("FlatpakAppID", ""), ("sortas", ""), ("tags", [])]


def add(cfg, vdf=None, running=None):
    """Add this copy of the app to Steam (or point its existing entry at this copy). -> {file, backup, updated}"""
    if (running or steam_running)():
        raise ValueError("Close Steam first (Steam > Exit). Steam rewrites its list of non-Steam games when it exits, "
                         "so a change made while it runs would be lost.")
    vdf = Path(vdf) if vdf else shortcuts_file()
    exe, args, folder, icon = shortcut.target(cfg)
    root, backup = [("shortcuts", [])], None
    if vdf.is_file():
        old = vdf.read_bytes()
        root = parse(old)
        backup = vdf.with_name(f"shortcuts.vdf.ronin-backup-{time.strftime('%Y%m%d-%H%M%S')}")
        backup.write_bytes(old)
    if not root or root[0][0].lower() != "shortcuts" or not isinstance(root[0][1], list):
        raise ValueError("Steam's shortcuts.vdf does not look like a list of non-Steam games; nothing was changed.")
    games = root[0][1]
    ours = lambda g: isinstance(g, list) and dict(g).get("AppName") == APP_NAME
    taken = {dict(g).get("appid", 0) & 0xFFFFFFFF for _, g in games if isinstance(g, list) and not ours(g)}
    mine = entry(exe, args, folder, icon.rsplit(",", 1)[0], taken=taken)
    updated = False
    for i, (k, g) in enumerate(games):
        if ours(g):
            keep = dict(g)   # keep what Steam or the user set on it: play time, hidden, overlay, tags
            games[i] = (k, [(f, keep.get(f, v) if f in ("LastPlayTime", "IsHidden", "AllowOverlay", "AllowDesktopConfig", "tags", "sortas") else v)
                            for f, v in mine])
            updated = True
            break
    else:
        n = 1 + max((int(k) for k, _ in games if k.isdigit()), default=-1)
        games.append((str(n), mine))
    vdf.parent.mkdir(parents=True, exist_ok=True)
    tmp = vdf.with_name(vdf.name + ".tmp")
    tmp.write_bytes(dumps(root))
    os.replace(tmp, vdf)
    return {"file": str(vdf), "backup": str(backup) if backup else "", "updated": updated}
