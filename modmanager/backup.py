"""Backup and restore of this app's own data, as one .zip file (for a new PC, or before trying something).

What goes in: the app-wide settings, the games you added, and for every game its playsets (with their Undo history and
recently deleted playsets), its library and the presets you saved. What stays out: mods, saves, the backups of
uninstalled mods, logos and caches; they are big, and they belong to the games or can be made again.

A backup is untrusted input when it is restored (it may come from anywhere): only the file names listed above are
accepted, every file must be a JSON object within a size limit, a playset file must load as one, and nothing is written
unless the whole archive passes. Before anything is replaced, the current data is saved as a backup of its own in
`app-backups/`, so a restore can always be undone by restoring that file.
"""
import io
import json
import re
import time
import zipfile
from pathlib import Path

from . import __version__
from .store import Store, _atomic_write

FORMAT = "ronin-mod-manager-backup"
MANIFEST = "backup.json"
MAX_FILE = 32 * 1024 * 1024
MAX_TOTAL = 128 * 1024 * 1024
MAX_FILES = 2000
KEEP_SAFETY = 10   # automatic "before restore" copies kept in app-backups/

_GAME = r"(?:cg-)?[a-z0-9][a-z0-9-]{0,39}"
ALLOWED = re.compile(rf"^(?:settings\.json|custom_games\.json|{_GAME}/(?:playsets\.json|library\.json|presets/[a-z0-9][a-z0-9_.-]{{0,79}}\.json))$")


class BadBackup(ValueError):
    pass


def _files(base):
    """(name in the backup, path on disk) for everything that is backed up."""
    base = Path(base)
    out = []
    for name in ("settings.json", "custom_games.json"):
        if (base / name).is_file():
            out.append((name, base / name))
    for d in sorted(p for p in base.iterdir() if p.is_dir() and not p.is_symlink()) if base.is_dir() else []:
        for name in ("playsets.json", "library.json"):
            f = d / name
            if f.is_file() and ALLOWED.match(f"{d.name}/{name}"):
                out.append((f"{d.name}/{name}", f))
        pre = d / "presets"
        if pre.is_dir():
            for f in sorted(pre.glob("*.json")):
                if f.is_file() and not f.is_symlink() and ALLOWED.match(f"{d.name}/presets/{f.name}"):
                    out.append((f"{d.name}/presets/{f.name}", f))
    return out


def make(base):
    """-> (zip bytes, [names in it])."""
    buf, names, total = io.BytesIO(), [], 0
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for name, f in _files(base):
            data = f.read_bytes()
            total += len(data)
            if len(data) > MAX_FILE or total > MAX_TOTAL:
                raise ValueError(f"{name} is too large to back up.")
            z.writestr(name, data)
            names.append(name)
        z.writestr(MANIFEST, json.dumps({"format": FORMAT, "version": 1, "app_version": __version__,
                                         "created": int(time.time()), "files": names}, indent=2))
    return buf.getvalue(), names


def read(data):
    """Check a backup completely. -> {name: parsed JSON}. Raises BadBackup with a readable reason."""
    try:
        z = zipfile.ZipFile(io.BytesIO(data))
    except (zipfile.BadZipFile, OSError, ValueError):
        raise BadBackup("That file is not a Ronin Mod Manager backup (it is not a .zip file).")
    out, total = {}, 0
    with z:
        infos = z.infolist()
        if len(infos) > MAX_FILES:
            raise BadBackup("That backup has too many files.")
        names = {i.filename for i in infos}
        if MANIFEST not in names:
            raise BadBackup("That .zip file is not a Ronin Mod Manager backup (it has no backup.json).")
        for i in infos:
            if i.is_dir():
                continue
            if i.filename != MANIFEST and not ALLOWED.match(i.filename):
                raise BadBackup(f"That backup holds a file it should not ({i.filename[:80]}), so nothing was restored.")
            if i.file_size > MAX_FILE:
                raise BadBackup(f"{i.filename} in that backup is too large.")
            try:
                with z.open(i) as f:
                    raw = f.read(MAX_FILE + 1)
            except (zipfile.BadZipFile, OSError, RuntimeError, NotImplementedError, EOFError) as e:
                raise BadBackup(f"That backup is damaged ({type(e).__name__}).")
            total += len(raw)
            if len(raw) > MAX_FILE or total > MAX_TOTAL:
                raise BadBackup("That backup expands to too much data.")
            try:
                doc = json.loads(raw.decode("utf-8-sig"))
            except ValueError:
                raise BadBackup(f"{i.filename} in that backup is damaged (not readable JSON).")
            if not isinstance(doc, dict):
                raise BadBackup(f"{i.filename} in that backup is not what this app writes.")
            out[i.filename] = doc
    head = out.pop(MANIFEST)
    if head.get("format") != FORMAT:
        raise BadBackup("That .zip file is not a Ronin Mod Manager backup.")
    if not isinstance(head.get("version"), int) or head["version"] > 1:
        raise BadBackup("That backup was made by a newer version of the app. Update the app first.")
    return out


def _check_playsets(name, doc, tmp):
    p = Path(tmp) / "check.json"
    p.write_text(json.dumps(doc), encoding="utf-8")
    try:
        Store(p)
    except ValueError:
        raise BadBackup(f"{name} in that backup is not a playset file.")


def restore(base, data):
    """Replace the app's data with a backup's. Games and files that are not in the backup are left as they are.
    -> {"restored": [names], "safety_copy": path of the backup made of the data as it was}"""
    import tempfile
    base = Path(base)
    files = read(data)
    with tempfile.TemporaryDirectory() as t:
        for name, doc in files.items():
            if name.endswith("/playsets.json"):
                _check_playsets(name, doc, t)
    safety_dir = base / "app-backups"
    safety_dir.mkdir(parents=True, exist_ok=True)
    now, _ = make(base)
    safety = safety_dir / f"before-restore-{time.strftime('%Y%m%d-%H%M%S')}.zip"
    n = 2
    while safety.exists():
        safety = safety_dir / f"before-restore-{time.strftime('%Y%m%d-%H%M%S')}-{n}.zip"
        n += 1
    safety.write_bytes(now)
    for old in sorted(safety_dir.glob("before-restore-*.zip"))[:-KEEP_SAFETY]:
        try:
            old.unlink()
        except OSError:
            pass
    for name, doc in files.items():
        target = base / Path(*name.split("/"))
        target.parent.mkdir(parents=True, exist_ok=True)
        _atomic_write(target, json.dumps(doc, indent=2))
    return {"restored": sorted(files), "safety_copy": str(safety)}


def filename():
    return f"RoninModManager-backup-{time.strftime('%Y-%m-%d')}.zip"
