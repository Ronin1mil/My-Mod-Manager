"""Safe installation of mods from .zip archives (and uninstall into a backup).

Archives are untrusted input. Rules (see docs/08-security.md): no path traversal, absolute or
drive paths, reserved names or alternate streams; no symlinks; no scripts/executables; hard caps
on entries, total size and compression ratio; extract to a staging dir, validate, then move.
"""
import re
import shutil
import stat
import struct
import tempfile
import time
import zipfile
import zlib
from pathlib import Path, PurePosixPath

from .paths import config_dir

MAX_ENTRIES = 20000
MAX_TOTAL = 4 * 1024**3
MAX_ENTRY = 1024**3
MAX_RATIO = 200  # compressed -> uncompressed, applied to entries over 1 MiB
BLOCKED_EXT = {".exe", ".dll", ".bat", ".cmd", ".ps1", ".vbs", ".vbe", ".wsf", ".hta", ".msi", ".lnk",
               ".scr", ".com", ".cpl", ".jar", ".reg", ".pif", ".sh", ".js", ".py", ".so", ".dylib"}
RESERVED = {"con", "prn", "aux", "nul", *(f"com{i}" for i in range(1, 10)), *(f"lpt{i}" for i in range(1, 10))}
FOLDER_OK = re.compile(r"^[A-Za-z0-9][A-Za-z0-9 _.\-]{0,79}$")


class UnsafeArchive(ValueError):
    pass


def safe_relative(name):
    """Validate an archive entry name; return the cleaned posix relative path."""
    if "\0" in name:
        raise UnsafeArchive("entry name contains a NUL byte")
    name = name.replace("\\", "/")
    if name.startswith("/") or re.match(r"^[A-Za-z]:", name):
        raise UnsafeArchive(f"absolute path in archive: {name}")
    parts = []
    for part in name.split("/"):
        if part in ("", "."):
            continue
        if part == "..":
            raise UnsafeArchive(f"path traversal in archive: {name}")
        if ":" in part or part.endswith((".", " ")) or part.split(".")[0].lower() in RESERVED \
                or any(ord(c) < 32 for c in part):
            raise UnsafeArchive(f"unsafe file name in archive: {part}")
        parts.append(part)
    return "/".join(parts)


CORRUPT = (zipfile.BadZipFile, zlib.error, EOFError, OSError, NotImplementedError, RuntimeError,
           struct.error, OverflowError)


def extract_zip(archive, dest):
    try:
        return _extract_zip(archive, dest)
    except UnsafeArchive:
        raise
    except CORRUPT as e:  # truncated/mutated/encrypted/unsupported archives
        raise UnsafeArchive(f"the archive is damaged or uses an unsupported format ({type(e).__name__})")


def _extract_zip(archive, dest):
    """Extract into `dest` (must exist). Returns list of relative file paths. Nothing outside dest is touched."""
    dest = Path(dest).resolve()
    files, total = [], 0
    try:
        zf = zipfile.ZipFile(archive)
    except (zipfile.BadZipFile, OSError) as e:
        raise UnsafeArchive(f"not a valid zip archive ({e})")
    with zf:
        infos = zf.infolist()
        if len(infos) > MAX_ENTRIES:
            raise UnsafeArchive("archive has too many files")
        for zi in infos:
            rel = safe_relative(zi.filename)
            if not rel:
                continue
            mode = zi.external_attr >> 16
            if stat.S_ISLNK(mode):
                raise UnsafeArchive(f"symbolic link in archive: {rel}")
            if zi.is_dir():
                (dest / rel).mkdir(parents=True, exist_ok=True)
                continue
            if PurePosixPath(rel).suffix.lower() in BLOCKED_EXT:
                raise UnsafeArchive(f"'{rel}' is an executable or script. mods never need these, "
                                    "so the archive was rejected.")
            if zi.file_size > MAX_ENTRY:
                raise UnsafeArchive(f"'{rel}' is too large")
            if zi.file_size > 1024**2 and zi.compress_size and zi.file_size / zi.compress_size > MAX_RATIO:
                raise UnsafeArchive(f"'{rel}' has a suspicious compression ratio (zip bomb?)")
            out = (dest / rel).resolve()
            if dest not in out.parents:
                raise UnsafeArchive(f"path escapes the target folder: {rel}")
            out.parent.mkdir(parents=True, exist_ok=True)
            written = 0
            with zf.open(zi) as src, open(out, "wb") as dst:  # count real bytes: declared sizes can lie
                while chunk := src.read(1024 * 256):
                    written += len(chunk)
                    total += len(chunk)
                    if written > MAX_ENTRY or total > MAX_TOTAL:
                        raise UnsafeArchive("archive expands to too much data")
                    dst.write(chunk)
            files.append(rel)
    return files


def find_mod_roots(base, depth=3):
    """Folders that look like a mod (have metadata.json or descriptor.mod)."""
    base, roots = Path(base), []

    def walk(d, level):
        if (d / ".metadata/metadata.json").is_file() or (d / "descriptor.mod").is_file():
            roots.append(d)
            return
        if level < depth:
            for c in sorted(d.iterdir()):
                if c.is_dir() and not c.is_symlink():
                    walk(c, level + 1)

    walk(base, 0)
    return roots


def _folder_name(root, base, archive_stem):
    n = root.name if root != base else archive_stem
    n = re.sub(r"[^A-Za-z0-9 _.\-]+", "_", n).strip(" .") or "mod"
    return n if FOLDER_OK.match(n) else "mod_" + n[:60]


def _esc(s):
    return str(s).replace("\\", "/").replace('"', "'")


def backup_dir(cfg=None):
    d = Path(cfg or config_dir()) / "backups"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _move_to_backup(path, label, cfg=None):
    dst = backup_dir(cfg) / f"{label}-{time.strftime('%Y%m%d-%H%M%S')}"
    n = 2
    while dst.exists():
        dst = backup_dir(cfg) / f"{label}-{time.strftime('%Y%m%d-%H%M%S')}-{n}"
        n += 1
    shutil.move(str(path), str(dst))
    return dst


def install_archive(archive, user_dir, archive_name="mod.zip", cfg=None):
    """Install a zip into <user_dir>/mod and write its .mod descriptor.
    Returns {installed: [{folder, name, upgraded}], warnings: []}."""
    from .descriptor import parse_metadata
    if not str(archive_name).lower().endswith(".zip"):
        raise ValueError("Only .zip archives are supported (extract 7z/rar mods and re-zip them).")
    mod_dir = Path(user_dir) / "mod"
    mod_dir.mkdir(parents=True, exist_ok=True)
    stage = Path(cfg or config_dir()) / "staging"
    stage.mkdir(parents=True, exist_ok=True)
    tmp = Path(tempfile.mkdtemp(dir=stage))
    try:
        extract_zip(archive, tmp)
        roots = find_mod_roots(tmp)
        if not roots:
            raise ValueError("This archive does not contain a mod "
                             "(no .metadata/metadata.json or descriptor.mod found).")
        stem = re.sub(r"\.zip$", "", Path(archive_name).name, flags=re.I)
        report = {"installed": [], "warnings": []}
        for root in roots:
            folder = _folder_name(root, tmp, stem)
            dest = mod_dir / folder
            upgraded = dest.exists()
            if upgraded:
                _move_to_backup(dest, folder, cfg)
            shutil.move(str(root), str(dest))
            meta = {}
            mf = dest / ".metadata/metadata.json"
            if mf.is_file():
                meta = parse_metadata(mf.read_text(encoding="utf-8-sig", errors="replace"))
            name = meta.get("name") or folder
            lines = [f'name="{_esc(name)}"', f'path="mod/{folder}"']
            if meta.get("version"):
                lines.append(f'version="{_esc(meta["version"])}"')
            if meta.get("supported_version"):
                lines.append(f'supported_version="{_esc(meta["supported_version"])}"')
            (mod_dir / f"{folder}.mod").write_text("\n".join(lines) + "\n", encoding="utf-8")
            report["installed"].append({"folder": folder, "name": name, "upgraded": upgraded,
                                        "id": f"local:{folder}"})
        return report
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def uninstall(user_dir, mod, cfg=None):
    """Move a local mod's folder and descriptor into the backup folder (never deletes)."""
    if mod["source"] != "local" or not mod["root"]:
        raise ValueError("Only mods installed in the local mod folder can be uninstalled here. "
                         "Unsubscribe Workshop mods in Steam.")
    mod_dir = (Path(user_dir) / "mod").resolve()
    root = Path(mod["root"]).resolve()
    if mod_dir not in root.parents:
        raise ValueError("This mod lives outside the mod folder; remove it manually.")
    stem = mod["id"].split(":", 1)[1]
    dest = _move_to_backup(root, root.name, cfg)
    desc = mod_dir / f"{stem}.mod"
    if desc.is_file():
        shutil.move(str(desc), str(dest) + ".mod")
    return str(dest)
