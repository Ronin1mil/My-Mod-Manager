"""One plain-text error log in its own folder inside the user's Documents (Documents/Ronin Mod Manager), so a problem can be read (and sent) without a console.

Written by the server (unexpected errors, crashes) and by the web page (script errors, failed requests) through
/api/client-error. Never raises, never grows past ~1 MB (one rotated copy), and records no mod contents or
personal data beyond the error text, game name and versions.
"""
import os
import platform
import sys
import threading
import time
import traceback
from pathlib import Path

from . import APP_NAME, __version__

LOG_NAME = "RoninModManager-errors.log"
LOG_DIR = APP_NAME
REPEAT_SECONDS = 30  # the same error again within this time is not written again (a failing page retries a lot)
MAX_BYTES = 1024 * 1024
MAX_ENTRY = 20000
_lock = threading.Lock()
_path = None
_recent = {}
_moved = False


def documents_dir():
    """The real Documents folder (follows OneDrive/redirected folders on Windows), else ~/Documents, else home."""
    override = os.environ.get("MODMANAGER_LOG_DIR")
    if override:
        return Path(override)
    if sys.platform == "win32":
        try:
            import ctypes
            buf = ctypes.c_wchar_p()
            guid = ctypes.create_string_buffer(16)
            # FOLDERID_Documents {FDD39AD0-238F-46AF-ADB4-6C85480369C7}
            ctypes.windll.ole32.CLSIDFromString("{FDD39AD0-238F-46AF-ADB4-6C85480369C7}", guid)
            if ctypes.windll.shell32.SHGetKnownFolderPath(guid, 0, None, ctypes.byref(buf)) == 0 and buf.value:
                p = Path(buf.value)
                ctypes.windll.ole32.CoTaskMemFree(buf)
                if p.is_dir():
                    return p
        except Exception:
            pass
    home = Path.home()
    return home / "Documents" if (home / "Documents").is_dir() else home


def log_path():
    global _path
    if _path is None or os.environ.get("MODMANAGER_LOG_DIR"):
        _path = documents_dir() / LOG_DIR / LOG_NAME
    return _path


def _move_old_log(p):
    """Versions up to 0.5.0 wrote the log straight into Documents: bring it into the folder once."""
    global _moved
    if _moved:
        return
    _moved = True
    old = p.parent.parent / LOG_NAME
    try:
        for suffix in ("", ".1"):
            src, dst = Path(str(old) + suffix), Path(str(p) + suffix)
            if src.is_file() and not dst.exists():
                os.replace(src, dst)
    except OSError:
        pass


def _header():
    return (f"{APP_NAME} {__version__} | Python {platform.python_version()} | {platform.platform()}"
            f"{' | frozen' if getattr(sys, 'frozen', False) else ''}")


def write(source, message, detail="", where=""):
    """Append one entry. Returns the log path (str), or '' if the file could not be written."""
    try:
        text = str(message)[:2000]
        entry = [f"=== {time.strftime('%Y-%m-%d %H:%M:%S')} [{source}] {text}"]
        if where:
            entry.append(f"where: {str(where)[:300]}")
        if detail:
            entry.append(str(detail)[:MAX_ENTRY])
        entry.append(_header())
        body = "\n".join(entry) + "\n\n"
        p = log_path()
        with _lock:
            now = time.time()
            key = (source, text, str(where)[:300])
            if now - _recent.get(key, -1e9) < REPEAT_SECONDS:
                return str(p)
            if len(_recent) > 500:
                _recent.clear()
            _recent[key] = now
            p.parent.mkdir(parents=True, exist_ok=True)
            _move_old_log(p)
            if p.is_file() and p.stat().st_size > MAX_BYTES:
                os.replace(p, p.with_suffix(".log.1"))
            with open(p, "a", encoding="utf-8", errors="replace") as f:
                f.write(body)
        return str(p)
    except Exception:
        return ""


def write_exception(source, exc, where=""):
    tb = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))
    return write(source, f"{type(exc).__name__}: {exc}", tb, where)


def install_hooks():
    """Log uncaught exceptions in the main and worker threads before the default handler runs."""
    prev, prev_t = sys.excepthook, threading.excepthook

    def hook(t, v, tb):
        write("crash", f"{t.__name__}: {v}", "".join(traceback.format_exception(t, v, tb)))
        prev(t, v, tb)

    def thook(args):
        write("thread", f"{args.exc_type.__name__}: {args.exc_value}",
              "".join(traceback.format_exception(args.exc_type, args.exc_value, args.exc_traceback)),
              getattr(args.thread, "name", ""))
        prev_t(args)

    sys.excepthook, threading.excepthook = hook, thook
