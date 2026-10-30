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
BATCH = 10                 # items per steamcmd login
RATE_LIMIT_WAIT = 30 * 60  # Steam does not say how long a login rate limit lasts; ~30 min is what people report
RATE_LIMIT_TRIES = 3


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


def failure_line(out):
    """The line that says why steamcmd failed: its last 'ERROR'/'failed' line, not the shutdown noise it prints after
    it (e.g. 'CWorkThreadPool::~CWorkThreadPool: work processing queue not empty')."""
    lines = [ln.strip() for ln in out.splitlines() if ln.strip()]
    why = [ln for ln in lines if "error" in ln.lower() or "failed" in ln.lower()]
    return ((why or lines or ["steamcmd failed"])[-1])[:200]


def is_rate_limited(out):
    o = out.lower()
    return "rate limit" in o or "ratelimit" in o


def _item_ok(out, wid):
    return any("success" in ln.lower() and f"item {wid}" in ln for ln in out.splitlines())


def _item_failure(out, wid):
    """Why this item failed: steamcmd's line about it ('ERROR! Download item <id> failed (...)'), else the run's error line."""
    mine = [ln.strip() for ln in out.splitlines() if f"item {wid}" in ln and ("error" in ln.lower() or "fail" in ln.lower())]
    return (mine[-1] if mine else failure_line(out))[:200]


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

    def start(self, steamcmd, user, ids, after=None):
        """`after(id, folder)`, when given, runs for each item that downloaded (e.g. to install it); an error there
        fails that item with its message."""
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
        t = threading.Thread(target=self._run, args=(job, exe, user, ids, after), daemon=True)
        t.start()
        job["thread"] = t
        return self.public(job)

    def _run(self, job, exe, user, ids, after=None):
        """Log in once per batch of BATCH items (not once per item: many logins in a row is what makes Steam answer
        'Rate Limit Exceeded'). When Steam does limit us, wait (job state 'waiting', with a countdown) and try the
        items that are left again, up to RATE_LIMIT_TRIES times; `retry_now` cuts a wait short."""
        job["state"], waits = "running", 0
        todo = list(ids)
        while todo:
            batch, todo = todo[:BATCH], todo[BATCH:]
            for wid in batch:
                job["items"][wid].update(state="running", message="")
            argv = [str(exe), "+login", user]
            for wid in batch:
                argv += ["+workshop_download_item", self.game.app_id, wid]
            argv.append("+quit")
            try:
                r = self.runner(argv, capture_output=True, text=True, timeout=min(STEAMCMD_TIMEOUT * len(batch), 4 * 3600),
                                cwd=str(exe.parent))
                out = (r.stdout or "") + (r.stderr or "")
            except (OSError, subprocess.SubprocessError) as e:
                for wid in batch:
                    job["items"][wid].update(state="failed", message=str(e)[:200])
                continue
            left = []
            for wid in batch:
                it = job["items"][wid]
                ok = _item_ok(out, wid) and (Path(job["dir"]) / wid).is_dir()
                it["state"], it["message"] = ("done", "") if ok else ("failed", _item_failure(out, wid))
                if ok and after:
                    try:
                        it["installed"] = after(wid, Path(job["dir"]) / wid)["folder"]
                    except Exception as e:   # downloaded, but not usable yet: say why
                        it["state"], it["message"] = "failed", f"Downloaded, but not installed: {e}"[:200]
                if not ok:
                    left.append(wid)
            if left and _needs_login(out):   # every other item would fail the same way: stop and say what to do
                msg = login_help(exe, user)
                for rest in job["items"].values():
                    if rest["state"] != "done":
                        rest["state"], rest["message"] = "failed", msg
                break
            if left and is_rate_limited(out):
                waits += 1
                if waits > RATE_LIMIT_TRIES:
                    for wid in left + todo:
                        job["items"][wid].update(state="failed", message="Steam kept limiting downloads (rate limit). Try again later.")
                    break
                for wid in left:
                    job["items"][wid].update(state="queued", message="waiting for Steam's rate limit")
                self._wait(job, RATE_LIMIT_WAIT * waits)
                todo = left + todo
        job["state"] = "done" if all(i["state"] == "done" for i in job["items"].values()) else "failed"

    def _wait(self, job, seconds):
        job["state"], job["retry_at"] = "waiting", time.time() + seconds
        ev = job.setdefault("wake", threading.Event())
        ev.clear()
        ev.wait(seconds)
        job["state"], job["retry_at"] = "running", None

    def retry_now(self, jid):
        """End a rate-limit wait early (the user pressed Retry now)."""
        job = self.jobs.get(str(jid))
        if not job or job["state"] != "waiting":
            raise ValueError("That download is not waiting.")
        job["wake"].set()
        return self.public(job)

    @staticmethod
    def public(job):
        out = {k: v for k, v in job.items() if k not in ("thread", "wake", "retry_at")}
        if job.get("retry_at"):
            out["retry_in"] = max(0, int(job["retry_at"] - time.time()))   # seconds: the page counts down from here
        return out

    def status(self):
        with self.lock:
            return [self.public(j) for j in self.jobs.values()]
