"""Build the Python edition: one file, Mod-Manager-python.pyzw, started by the Python launcher (py / pythonw).

    python tools/build_pyz.py [output]        (default: dist/Mod-Manager-python.pyzw)

Why it exists: Windows Smart App Control blocks every unsigned .exe, but runs the signed python.exe. The app is
plain standard-library Python, so this file is just the `modmanager` package in a zip plus a small bootstrap.

The bootstrap unpacks the package once into a cache folder (named after the file's SHA-256, so a new version gets
its own) and runs it from there, because the app reads its page and presets as ordinary files, which a zip cannot
give it. It also tells the app which file it is (MODMANAGER_PYZ), so the in-app updater can replace that file.
"""
import shutil
import sys
import tempfile
import zipapp
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

BOOTSTRAP = r'''"""Start Ronin Mod Manager from this zip app (see tools/build_pyz.py)."""
import hashlib
import os
import runpy
import shutil
import sys
import time
import zipfile


def _cache_root():
    base = os.environ.get("MODMANAGER_PYZ_CACHE")
    if base:
        return base
    root = os.environ.get("LOCALAPPDATA") if sys.platform == "win32" else (os.environ.get("XDG_CACHE_HOME") or os.path.join(os.path.expanduser("~"), ".cache"))
    return os.path.join(root or os.path.expanduser("~"), "Ronin Mod Manager", "pyz")


def _unpack(archive):
    with open(archive, "rb") as f:
        digest = hashlib.sha256(f.read()).hexdigest()[:16]
    base = _cache_root()
    dest = os.path.join(base, digest)
    if not os.path.isfile(os.path.join(dest, "modmanager", "__init__.py")):
        os.makedirs(base, exist_ok=True)
        tmp = f"{dest}.part{os.getpid()}"
        shutil.rmtree(tmp, ignore_errors=True)
        with zipfile.ZipFile(archive) as z:
            for name in z.namelist():
                if name.startswith("modmanager/") and ".." not in name.split("/"):
                    z.extract(name, tmp)
        try:
            os.replace(tmp, dest)
        except OSError:   # another start unpacked the same version first
            shutil.rmtree(tmp, ignore_errors=True)
    for d in os.listdir(base):   # old versions: remove those untouched for a week (one in use cannot be removed; that is fine)
        p = os.path.join(base, d)
        if d != digest and os.path.isdir(p) and time.time() - os.path.getmtime(p) > 7 * 86400:
            shutil.rmtree(p, ignore_errors=True)
    return dest


archive = os.path.dirname(os.path.abspath(__file__))
if not os.path.isfile(archive):
    raise SystemExit("Start this file with the Python launcher: py Mod-Manager-python.pyzw")
sys.path.insert(0, _unpack(archive))
os.environ["MODMANAGER_PYZ"] = archive
runpy.run_module("modmanager", run_name="__main__", alter_sys=True)
'''


def build(out):
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as t:
        stage = Path(t) / "app"
        shutil.copytree(ROOT / "modmanager", stage / "modmanager",
                        ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
        (stage / "__main__.py").write_text(BOOTSTRAP, encoding="utf-8")
        out.unlink(missing_ok=True)
        zipapp.create_archive(stage, out, interpreter="/usr/bin/env python3", compressed=True)
    return out


if __name__ == "__main__":
    target = build(sys.argv[1] if len(sys.argv) > 1 else ROOT / "dist" / "Mod-Manager-python.pyzw")
    print(f"{target}  ({target.stat().st_size // 1024} KB)")
