"""Timestamped activity log for finding out what is slow or stuck.

One line per event, with millisecond timestamps and the thread, in <Documents>/Ronin Mod Manager/
RoninModManager-activity.log (next to the error log; ~2 MB, one rotated copy). Operations that can take a while
write a `>` line when they start and a `<` line with their duration when they end, so a hang shows as a `>` with no
matching `<`.

On for test builds (nightly) and whenever MODMANAGER_ACTIVITY_LOG=1; off in releases (MODMANAGER_ACTIVITY_LOG=0 forces
it off). Never raises and never records mod contents: only operation names, counts and timings.
"""
import os
import threading
import time
from contextlib import contextmanager

from . import BUILD, errorlog

LOG_NAME = "RoninModManager-activity.log"
MAX_BYTES = 2 * 1024 * 1024
_lock = threading.Lock()
_size = None  # bytes written so far to the current file (None = not looked at yet)


def enabled():
    flag = os.environ.get("MODMANAGER_ACTIVITY_LOG")
    return flag == "1" if flag in ("0", "1") else bool(BUILD)


def log_path():
    return errorlog.log_path().parent / LOG_NAME


def log(message):
    """Append one line. Safe to call from any thread."""
    global _size
    if not enabled():
        return
    try:
        now = time.time()
        line = (f"{time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(now))}.{int(now * 1000) % 1000:03d} "
                f"[{threading.current_thread().name}] {message}\n")
        with _lock:
            p = log_path()
            p.parent.mkdir(parents=True, exist_ok=True)
            if _size is None or not p.exists():
                _size = p.stat().st_size if p.exists() else 0
            if _size > MAX_BYTES:
                os.replace(p, p.with_name(p.name + ".1"))
                _size = 0
            with open(p, "a", encoding="utf-8") as f:
                f.write(line)
            _size += len(line.encode("utf-8"))
    except Exception:
        pass


class _Timer:
    def __init__(self, label, quiet):
        self.label, self.quiet, self.info = label, quiet, ""
        self.t0 = time.perf_counter()

    def note(self, **kv):
        """Add facts (counts, sizes) to the closing line."""
        self.info += "".join(f" {k}={v}" for k, v in kv.items())


@contextmanager
def timed(label, quiet=False, **kv):
    """Time a block. `quiet` skips the start line (for fast operations that only matter when slow)."""
    if not enabled():
        yield _Timer(label, True)
        return
    t = _Timer(label, quiet)
    t.note(**kv)
    if not quiet:
        log(f"> {label}{t.info}")
    status = "ok"
    try:
        yield t
    except BaseException as e:
        status = f"FAILED {type(e).__name__}"
        raise
    finally:
        ms = (time.perf_counter() - t.t0) * 1000
        log(f"< {label} {ms:.1f} ms{'' if status == 'ok' else ' ' + status}{t.info}")
