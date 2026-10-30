"""Getting Workshop mods onto this PC.

Two ways, both started only by an explicit user action:
  * Steam page  - open steam://url/CommunityFilePage/<id> so the Steam client shows the item; the user
                  presses Subscribe and Steam downloads it into the normal Workshop folder.
  * steamcmd    - optional. If the user configured a steamcmd executable (and a Steam account name whose
                  login steamcmd has cached), mods are fetched with `+workshop_download_item`.
                  No password is ever asked for, stored or sent by this app.
Nothing is run through a shell; ids and the account name are validated first.
"""
import re
import subprocess
import threading
import time
import webbrowser
from pathlib import Path

ID_RE = re.compile(r"^\d{1,20}$")
USER_RE = re.compile(r"^[A-Za-z0-9_.\-]{2,64}$")
MAX_IDS = 300
STEAMCMD_TIMEOUT = 30 * 60


def clean_ids(ids):
    if not isinstance(ids, list) or not 0 < len(ids) <= MAX_IDS:
        raise ValueError(f"Give 1-{MAX_IDS} Workshop ids.")
    out = []
    for i in ids:
        if not isinstance(i, (str, int)) or isinstance(i, bool) or not ID_RE.match(str(i)):
            raise ValueError(f"'{i}' is not a Workshop id (digits only).")
        out.append(str(i))
    return list(dict.fromkeys(out))


def page_url(wid):
    return f"steam://url/CommunityFilePage/{wid}"


def open_pages(ids, opener=None, delay=0.4):
    """Ask Steam to show each item's page. Returns the urls opened."""
    opener = opener or webbrowser.open
    urls = []
    for wid in clean_ids(ids):
        opener(page_url(wid))
        urls.append(page_url(wid))
        time.sleep(delay if delay and len(ids) > 1 else 0)
    return urls


def validate_steamcmd(path, user):
    p = Path(path) if path else None
    if not p or not p.is_file():
        raise ValueError("steamcmd was not found. Set its path in Settings, or use 'Open in Steam' instead.")
    if not USER_RE.match(str(user or "")):
        raise ValueError("Set your Steam account name in Settings first (steamcmd must already be logged in once).")
    return p


def steamcmd_candidates():
    """Where people usually unzip steamcmd (Valve's guide suggests C:\\steamcmd), in the order they are tried."""
    import os
    import shutil
    import sys
    home = Path.home()
    found = shutil.which("steamcmd")
    out = [Path(found)] if found else []
    if sys.platform == "win32":
        from .paths import _fixed_drives
        dirs = [Path(f"{d}:/") / n for d in _fixed_drives() for n in ("steamcmd", "SteamCMD", "Games/steamcmd", "Tools/steamcmd")]
        for env in ("ProgramFiles", "ProgramFiles(x86)", "LOCALAPPDATA", "APPDATA"):
            if os.environ.get(env):
                dirs.append(Path(os.environ[env]) / "steamcmd")
        for d in ("", "Downloads", "Desktop", "Documents"):
            dirs += [home / d / "steamcmd", home / d / "steamcmd_win32"]
            out.append(home / d / "steamcmd.exe")
        out += [d / "steamcmd.exe" for d in dirs]
    else:
        out += [home / "steamcmd/steamcmd.sh", home / ".steam/steamcmd/steamcmd.sh", home / "Steam/steamcmd.sh",
                Path("/usr/games/steamcmd"), Path("/usr/bin/steamcmd"), Path("/usr/local/bin/steamcmd")]
    return list(dict.fromkeys(out))


def find_steamcmd():
    """The first steamcmd executable in the usual places, or None. Only looks; never runs it."""
    for p in steamcmd_candidates():
        try:
            if p.is_file():
                return p
        except OSError:
            continue
    return None


def steamcmd_accounts(exe):
    """Account names steamcmd has a cached login for (from its config/config.vdf "Accounts" block). Names only."""
    try:
        text = (Path(exe).parent / "config" / "config.vdf").read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []
    tokens = re.findall(r'"((?:[^"\\]|\\.)*)"|([{}])', text)
    names, depth, at = [], 0, None
    for i, (word, brace) in enumerate(tokens):
        if brace == "{":
            depth += 1
            if at is None and i and tokens[i - 1][0].lower() == "accounts":
                at = depth
            elif at is not None and depth == at + 1 and i and tokens[i - 1][0]:
                names.append(tokens[i - 1][0])
        elif brace == "}":
            if depth == at:
                break
            depth -= 1
    return [n for n in names if USER_RE.match(n)]


_LOGIN_ERRORS = ("cached credentials not found", "login failure", "invalid password", "two-factor", "steam guard",
                 "account logon denied", "password:")


def _needs_login(out):
    o = out.lower()
    return any(e in o for e in _LOGIN_ERRORS)


def login_help(exe, user):
    """steamcmd had no saved login for this account. The app never handles passwords, so the user logs in once."""
    return (f"steamcmd is not logged in as '{user}' yet. Log in once yourself: open a terminal and run "
            f"\"{exe}\" +login {user} +quit, type your password and Steam Guard code there, then press Download again. "
            "After that steamcmd remembers the login.")


def content_dir(steamcmd, game):
    """Where steamcmd puts downloads: next to its executable."""
    return Path(steamcmd).resolve().parent / "steamapps" / "workshop" / "content" / game.app_id


class Downloads:
    """Background steamcmd jobs for one game. Jobs report progress; the request that started them returns at once."""

    def __init__(self, game, runner=None):
        self.game, self.runner = game, runner or subprocess.run
        self.jobs = {}
        self.lock = threading.Lock()
        self._n = 0

    def start(self, steamcmd, user, ids):
        exe = validate_steamcmd(steamcmd, user)
        ids = clean_ids(ids)
        with self.lock:
            if any(j["state"] in ("queued", "running") for j in self.jobs.values()):
                raise ValueError("A download is already running. Wait for it to finish.")
            self._n += 1
            jid = str(self._n)
            job = {"id": jid, "state": "queued", "items": {i: {"state": "queued", "message": ""} for i in ids},
                   "dir": str(content_dir(exe, self.game))}
            self.jobs[jid] = job
        t = threading.Thread(target=self._run, args=(job, exe, user, ids), daemon=True)
        t.start()
        job["thread"] = t
        return self.public(job)

    def _run(self, job, exe, user, ids):
        job["state"] = "running"
        for wid in ids:
            it = job["items"][wid]
            it["state"] = "running"
            argv = [str(exe), "+login", user, "+workshop_download_item", self.game.app_id, wid, "+quit"]
            try:
                r = self.runner(argv, capture_output=True, text=True, timeout=STEAMCMD_TIMEOUT, cwd=str(exe.parent))
                out = (r.stdout or "") + (r.stderr or "")
                ok = r.returncode == 0 and "Success" in out and (Path(job["dir"]) / wid).is_dir()
                it["state"] = "done" if ok else "failed"
                it["message"] = "" if ok else (out.strip().splitlines() or ["steamcmd failed"])[-1][:200]
                if not ok and _needs_login(out):   # every other item would fail the same way: stop and say what to do
                    msg = login_help(exe, user)
                    for rest in job["items"].values():
                        if rest["state"] != "done":
                            rest["state"], rest["message"] = "failed", msg
                    break
            except (OSError, subprocess.SubprocessError) as e:
                it["state"], it["message"] = "failed", str(e)[:200]
        job["state"] = "done" if all(i["state"] == "done" for i in job["items"].values()) else "failed"

    @staticmethod
    def public(job):
        return {k: v for k, v in job.items() if k != "thread"}

    def status(self):
        with self.lock:
            return [self.public(j) for j in self.jobs.values()]
