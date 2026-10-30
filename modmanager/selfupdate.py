"""Update the packaged app from this project's GitHub releases. Only for the downloaded single-file app
(a PyInstaller build); a source checkout is told to use git or the ZIP instead.

Flow, started only by the user pressing "Update now":
  1. ask GitHub for the latest release (update.check_for_update) and pick this platform's file
  2. download it next to the running app (https; github.com / *.githubusercontent.com only; size capped)
  3. verify its SHA-256 against the release's SHA256SUMS.txt - refuse on any mismatch or missing entry
  4. start the new file once (--version) to learn whether Windows lets it run: Smart App Control and antivirus refuse
     unsigned downloads at that point, and then nothing is changed
  5. swap it in (the old copy is kept as <name>.old until the next start) and start the new version; if that copy
     cannot start or ends at once, the old one is put back
The hash proves the download is intact and is the file the release lists. It is not a signature: someone
who can publish releases in the repo can publish a matching hash. Keep the repository's write access tight.
"""
import hashlib
import os
import re
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

from . import errorlog, perflog
from .update import ALLOWED_HOST, check_for_update, check_nightly, stable_current

MAX_EXE = 300 * 1024 * 1024
SUMS_NAME = "SHA256SUMS.txt"
PYZ_ASSET = "Mod-Manager-python.pyzw"   # the Python edition: one zip app run by py/pythonw, no exe of ours
SAFE_NAME = re.compile(r"^[A-Za-z0-9._\-]{1,100}$")


def frozen():
    return bool(getattr(sys, "frozen", False))


def pyz_path():
    """The Python edition's file (Mod-Manager-python.pyzw) when this copy was started from it, else None.
    Its bootstrap (tools/build_pyz.py) sets MODMANAGER_PYZ."""
    p = os.environ.get("MODMANAGER_PYZ")
    return Path(p) if p and Path(p).is_file() else None


def platform_asset():
    """File name of this copy's build in a release."""
    if pyz_path():
        return PYZ_ASSET
    if sys.platform == "win32":
        return "Mod-Manager-windows.exe"
    if sys.platform == "darwin":
        return "Mod-Manager-macos"
    return "Mod-Manager-linux"


def app_file():
    """The file an update replaces: the Python edition's zip app, or the packaged exe."""
    return pyz_path() or Path(sys.executable)


def can_self_update():
    return bool(pyz_path()) or (frozen() and Path(sys.executable).is_file())


def _host_ok(url):
    u = urllib.parse.urlparse(url)
    h = (u.hostname or "").lower()
    return u.scheme == "https" and (h in ("github.com", ALLOWED_HOST) or h.endswith(".githubusercontent.com"))


class _Redirects(urllib.request.HTTPRedirectHandler):
    """Follow GitHub's redirect to its CDN, but only to GitHub hosts, and never forward the token there."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        if not _host_ok(newurl):
            raise urllib.error.URLError(f"refusing to follow a redirect to {urllib.parse.urlparse(newurl).hostname}")
        nr = super().redirect_request(req, fp, code, msg, headers, newurl)
        if nr is not None and urllib.parse.urlparse(newurl).hostname != ALLOWED_HOST:
            nr.headers.pop("Authorization", None)
            nr.unredirected_hdrs.pop("Authorization", None)
        return nr


def download(url, dest, limit=MAX_EXE, token=None, timeout=60):
    """Stream `url` to `dest`. Returns the SHA-256 hex digest of what was written."""
    if not _host_ok(url) or not url.startswith(("https://github.com/", f"https://{ALLOWED_HOST}/")):
        raise ValueError("Updates are only downloaded from this project's GitHub releases.")
    headers = {"User-Agent": "modmanager-self-update", "Accept": "application/octet-stream"}
    if token and url.startswith(f"https://{ALLOWED_HOST}/"):
        headers["Authorization"] = f"Bearer {token}"
    op = urllib.request.build_opener(_Redirects)
    h, n = hashlib.sha256(), 0
    try:
        with op.open(urllib.request.Request(url, headers=headers), timeout=timeout) as r, open(dest, "wb") as f:
            while True:
                chunk = r.read(1024 * 256)
                if not chunk:
                    break
                n += len(chunk)
                if n > limit:
                    raise ValueError("The download is larger than expected; stopped.")
                h.update(chunk)
                f.write(chunk)
    except urllib.error.HTTPError as e:
        raise ValueError(f"GitHub answered {e.code} when downloading the update.")
    except (urllib.error.URLError, OSError) as e:
        raise ValueError(f"Could not download the update: {getattr(e, 'reason', e)}")
    if n == 0:
        raise ValueError("The download was empty.")
    return h.hexdigest()


def parse_sums(text):
    """'<hex>  <name>' lines (sha256sum format, also PowerShell's 'name hash') -> {name: hex}."""
    out = {}
    for line in str(text).splitlines():
        m = re.match(r"^\s*([0-9a-fA-F]{64})\s+\*?(\S+)\s*$", line) or re.match(r"^\s*(\S+)\s+([0-9a-fA-F]{64})\s*$", line)
        if m:
            a, b = m.groups()
            h, name = (a, b) if re.fullmatch(r"[0-9a-fA-F]{64}", a) else (b, a)
            out[Path(name).name] = h.lower()
    return out


def _asset_url(a, token):
    if token and a.get("api_url"):
        return a["api_url"]
    return a["url"]


def swap(exe, new):
    """Put `new` in place of the running `exe`. The old file stays as <exe>.old (removed on the next start). If an
    earlier <exe>.old cannot be removed (it can be a program that is still running, left by an update whose restart
    failed) the next free name .old1, .old2, ... is used instead of failing with "Access is denied"."""
    exe, new = Path(exe), Path(new)
    old = None
    for suffix in (".old", *(f".old{n}" for n in range(1, 6))):
        cand = exe.with_name(exe.name + suffix)
        try:
            if cand.exists():
                cand.unlink()
            old = cand
            break
        except OSError:
            continue
    if old is None:
        raise PermissionError("Older copies of this app are still running. Close them (check Task Manager) and try again.")
    if sys.platform != "win32":
        os.chmod(new, 0o755)
    os.replace(exe, old)  # a running program can be renamed (not overwritten) on Windows; fine everywhere else
    try:
        os.replace(new, exe)
    except OSError:
        os.replace(old, exe)  # undo: never leave the user without a program
        raise
    return old


def unswap(exe, old):
    """Undo swap(): the new file goes aside and the previous version is back under its own name."""
    exe, old = Path(exe), Path(old)
    bad = exe.with_name(exe.name + ".bad")
    try:
        bad.unlink(missing_ok=True)
        os.replace(exe, bad)
    except OSError:
        pass
    os.replace(old, exe)
    try:
        bad.unlink(missing_ok=True)
    except OSError:
        pass


def can_run(path):
    """May this file start on this PC? -> (ok, reason). A new download is started once with --version before it
    replaces anything: Smart App Control ("An Application Control policy has blocked this file", error 4551) and
    antivirus refuse an unsigned program when it is started, not when it is downloaded."""
    flags = 0x08000000 if sys.platform == "win32" else 0  # CREATE_NO_WINDOW
    cmd = [sys.executable, str(path)] if pyz_path() else [str(path)]   # the Python edition is started by the interpreter
    try:
        r = subprocess.run([*cmd, "--version"], env=child_environment(), capture_output=True, timeout=90,
                           stdin=subprocess.DEVNULL, creationflags=flags, cwd=str(Path(path).parent))
    except subprocess.TimeoutExpired:
        return True, ""   # it started (a slow first unpack); a blocked file fails at once
    except OSError as e:
        return False, str(e)
    return (True, "") if r.returncode == 0 else (False, f"it ended with exit code {r.returncode}")


def cleanup_old():
    """Remove the previous version left by an update. Called at start-up; never raises."""
    if frozen() or pyz_path():
        f = app_file()
        for suffix in (".old", *(f".old{n}" for n in range(1, 6))):
            try:
                f.with_name(f.name + suffix).unlink()
            except OSError:
                pass


def child_environment():
    """Environment for the new copy. A one-file PyInstaller app leaves variables that tell a child of the same app to
    reuse THIS copy's unpacked files; the new version must unpack its own (the old copy's folder lacks libraries the
    new one needs, e.g. _sqlite3 after 0.5.0)."""
    env = {k: v for k, v in os.environ.items() if k != "_MEIPASS2" and not k.startswith("_PYI_")}
    env.update(MODMANAGER_RESTARTED="1", PYINSTALLER_RESET_ENVIRONMENT="1")
    return env


def restart(exe, argv):
    """Start the new version (it waits for this one's port) and leave."""
    env = child_environment()
    flags = 0
    if sys.platform == "win32":
        flags = 0x00000008 | 0x00000200  # DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP
    args = ([sys.executable] if pyz_path() else []) + [str(exe)] + [a for a in argv if a != "--no-browser"]
    if os.environ.get("MODMANAGER_MODE") != "window":  # a window closes with the old copy, so the new one opens its own
        args.append("--no-browser")                       # a browser tab is still open and reloads itself
    return subprocess.Popen(args, env=env, close_fds=True, creationflags=flags, cwd=str(Path(exe).parent))


class Updater:
    """One update at a time, run in a worker thread; the page polls `status`."""

    def __init__(self, check=None, dl=download, exe=None, argv=None, restarter=restart, exiter=None, check_nightly_=None, verify=None):
        self.check = check or (lambda: check_for_update(stable_current()))
        self.check_nightly = check_nightly_ or check_nightly
        self.check_release = lambda: check_for_update("0.0.0")   # "go back": the newest release counts as newer than anything
        self.channel = "stable"
        self.dl, self.restarter = dl, restarter
        self.verify = verify or (can_run if frozen() or pyz_path() else None)   # a source checkout / a test has nothing to test-start
        self.exe = exe or str(app_file())
        self.argv = list(argv if argv is not None else sys.argv[1:])
        self.exiter = exiter or (lambda: os._exit(0))
        self.lock = threading.Lock()
        self.state = {"status": "idle", "message": ""}

    def status(self):
        return dict(self.state)

    def _set(self, status, message=""):
        self.state = {"status": status, "message": message}

    def start(self, run_async=True, channel="stable"):
        if not can_self_update() and self.exe == str(app_file()):
            raise ValueError("This copy runs from source, so it cannot replace itself. Update with Git "
                             "(git pull) or download the ZIP again. The downloadable app updates itself.")
        if not self.lock.acquire(blocking=False):
            return self.status()
        self.channel = channel if channel in ("nightly", "release") else "stable"
        self._set("working", "Checking for the newest test build…" if self.channel == "nightly" else "Checking for the newest version…")
        if run_async:
            threading.Thread(target=self._run, daemon=True, name="self-update").start()
        else:
            self._run()
        return self.status()

    def _run(self):
        token = os.environ.get("MODMANAGER_GITHUB_TOKEN") or None
        exe = Path(self.exe)
        new = exe.with_name(exe.name + ".new")
        try:
            perflog.log(f"update ({self.channel}): checking")
            info = {"nightly": self.check_nightly, "release": self.check_release}.get(self.channel, self.check)()
            if not info.get("update_available"):
                return self._set("current", info.get("message") or "You are up to date.")
            by = {a["name"]: a for a in info.get("assets", []) if SAFE_NAME.match(a.get("name", ""))}
            want = platform_asset()
            if want not in by or SUMS_NAME not in by:
                return self._set("error", f"Release {info.get('latest')} has no {want if want not in by else SUMS_NAME}. "
                                 "Download the update from the release page instead.")
            self._set("working", f"Downloading version {info['latest']}…")
            sums_tmp = exe.with_name(exe.name + ".sums")
            try:
                self.dl(_asset_url(by[SUMS_NAME], token), sums_tmp, 1024 * 1024, token)
                sums = parse_sums(sums_tmp.read_text(encoding="utf-8", errors="replace"))
            finally:
                sums_tmp.unlink(missing_ok=True)
            expected = sums.get(want)
            if not expected:
                return self._set("error", f"{SUMS_NAME} does not list {want}; the update was not installed.")
            with perflog.timed("update: download the app", size=by[want].get("size", 0)):
                got = self.dl(_asset_url(by[want], token), new, MAX_EXE, token)
            self._set("working", "Verifying the download…")
            if got != expected:
                new.unlink(missing_ok=True)
                return self._set("error", "The downloaded file does not match its published checksum, so it was "
                                 "discarded and nothing was changed.")
            if self.verify:
                self._set("working", "Checking that Windows lets the new version start…")
                with perflog.timed("update: test-start the new file"):
                    ok, why = self.verify(new)
                if not ok:
                    new.unlink(missing_ok=True)
                    perflog.log(f"update: the new file cannot start ({why})")
                    return self._set("error", f"Windows would not start the new version ({why}). That is usually Smart App Control or "
                                     "antivirus blocking a program that is not signed. Nothing was changed: you are still on the "
                                     "version you had.")
            with perflog.timed("update: swap in the new file"):
                old = swap(exe, new)
            self._set("restarting", f"Updated to {info['latest']}. Restarting…")
            perflog.log("update: starting the new copy, this one exits in 1.5 s")
            bad = None
            try:
                proc = self.restarter(exe, self.argv)
            except OSError as e:
                proc, bad = None, str(e)
            for _ in range(30 if proc is not None else 0):   # a copy that is blocked or crashes at once is seen within 3 s
                if proc.poll() is not None:
                    bad = f"it ended at once with exit code {proc.returncode}"
                    break
                time.sleep(0.1)
            if bad:
                unswap(exe, old)
                perflog.log(f"update: the new copy did not start ({bad}); the old one was put back")
                return self._set("error", f"The new version could not be started ({bad}). The previous version was put back, "
                                 "nothing is lost.")
            threading.Timer(1.5, self.exiter).start()
        except Exception as e:
            try:
                new.unlink(missing_ok=True)
            except OSError:
                pass
            errorlog.write_exception("update", e)
            self._set("error", str(e) if isinstance(e, ValueError) else f"{type(e).__name__}: {e}")
        finally:
            self.lock.release()
