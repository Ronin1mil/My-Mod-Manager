"""Update check against the project's GitHub repo. Runs only when the user asks (button or --check-update).

Network rules (docs/07-security.md): HTTPS to api.github.com only, size-capped, short timeout. A token is
read from MODMANAGER_GITHUB_TOKEN if the repo is private; it is sent only to api.github.com and never stored
or shown. Nothing is downloaded or installed: the result links to the release page for the user to open.
"""
import json
import os
import re
import urllib.error
import urllib.request

from . import __version__

REPO = "Ronin1mil/My-Mod-Manager"
API = "https://api.github.com"
ALLOWED_HOST = "api.github.com"
MAX_BYTES = 1024 * 1024
LINK_PREFIX = f"https://github.com/{REPO}/"
VERSION_RE = re.compile(r"^v?(\d+)\.(\d+)(?:\.(\d+))?(?:[-+.]?([0-9A-Za-z][0-9A-Za-z.\-]*))?$")


def parse_version(text):
    """'v1.2.3', '1.2', '1.2.3-beta.1' -> (1, 2, 3, 'beta.1'); None if it is not a version."""
    m = VERSION_RE.match(str(text or "").strip())
    if not m:
        return None
    return int(m.group(1)), int(m.group(2)), int(m.group(3) or 0), m.group(4) or ""


def _key(v):
    major, minor, patch, pre = v
    # a prerelease sorts below its release; prereleases compare by dotted parts, numbers numerically
    parts = [(0, int(p), "") if p.isdigit() else (1, 0, p) for p in re.split(r"[.\-]", pre)] if pre else []
    return (major, minor, patch, 0 if pre else 1, parts)


def is_newer(latest, current):
    a, b = parse_version(latest), parse_version(current)
    return bool(a and b and _key(a) > _key(b))


def default_fetch(url, token=None, timeout=10):
    """GET -> (status, parsed JSON or None). Only api.github.com over https; response size is capped."""
    if not url.startswith(f"https://{ALLOWED_HOST}/"):
        raise ValueError("Update checks are limited to https://api.github.com")
    headers = {"Accept": "application/vnd.github+json", "User-Agent": "modmanager-update-check",
               "X-GitHub-Api-Version": "2022-11-28"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            status, raw = r.status, r.read(MAX_BYTES + 1)
    except urllib.error.HTTPError as e:
        status, raw = e.code, e.read(MAX_BYTES + 1)
    if len(raw) > MAX_BYTES:
        raise ValueError("Response too large")
    try:
        return status, json.loads(raw.decode("utf-8", "replace")) if raw else None
    except ValueError:
        return status, None


def _clean_url(url, fallback):
    return url if isinstance(url, str) and url.startswith(LINK_PREFIX) else fallback


def _result(current, status, message, **kw):
    return {"current": current, "latest": None, "update_available": False, "status": status,
            "message": message, "url": f"{LINK_PREFIX}releases", "notes": "", "published": "", "assets": [], **kw}


def check_for_update(current=__version__, fetch=None, repo=REPO):
    """Compare the running version with the newest GitHub release (falling back to tags).
    Never raises: failures come back as a result with status 'unreachable' or 'error'."""
    token = os.environ.get("MODMANAGER_GITHUB_TOKEN") or None
    fetch = fetch or (lambda u: default_fetch(u, token))
    try:
        status, rel = fetch(f"{API}/repos/{repo}/releases/latest")
        if status == 200 and isinstance(rel, dict) and parse_version(rel.get("tag_name")):
            tag = rel["tag_name"]
            assets = [{"name": a["name"][:100], "url": a["browser_download_url"], "size": int(a.get("size") or 0),
                       "api_url": f"{API}/repos/{repo}/releases/assets/{int(a['id'])}" if str(a.get("id", "")).isdigit() else ""}
                      for a in rel.get("assets") or []
                      if isinstance(a, dict) and isinstance(a.get("name"), str)
                      and str(a.get("browser_download_url", "")).startswith(LINK_PREFIX)]
            newer = is_newer(tag, current)
            return _result(current, "update" if newer else "current",
                           f"Version {tag.lstrip('v')} is available." if newer else "You are up to date.",
                           latest=tag.lstrip("v"), update_available=newer,
                           url=_clean_url(rel.get("html_url"), f"{LINK_PREFIX}releases"),
                           notes=str(rel.get("body") or "")[:4000], published=str(rel.get("published_at") or "")[:10],
                           assets=assets, prerelease=bool(rel.get("prerelease")))
        if status in (200, 404):  # no published release: look at tags
            tstatus, tags = fetch(f"{API}/repos/{repo}/tags?per_page=50")
            if tstatus == 200 and isinstance(tags, list):
                versions = [t["name"] for t in tags if isinstance(t, dict) and parse_version(t.get("name"))]
                if not versions:
                    return _result(current, "no_releases", "No releases have been published yet.")
                best = max(versions, key=lambda v: _key(parse_version(v)))
                newer = is_newer(best, current)
                return _result(current, "update" if newer else "current",
                               f"Version {best.lstrip('v')} is available." if newer else "You are up to date.",
                               latest=best.lstrip("v"), update_available=newer,
                               url=f"{LINK_PREFIX}releases/tag/{best}" if re.match(r"^[\w.\-+]+$", best)
                               else f"{LINK_PREFIX}releases")
            if tstatus == 404:
                return _result(current, "unreachable", "The repository was not found. If it is private, set the "
                               "MODMANAGER_GITHUB_TOKEN environment variable to a token that can read it.")
        if status in (401, 403):
            return _result(current, "unreachable", "GitHub refused the request (rate limit or missing access). "
                           "For a private repository set MODMANAGER_GITHUB_TOKEN. Try again later.")
        return _result(current, "error", f"Unexpected response from GitHub (HTTP {status}).")
    except (urllib.error.URLError, OSError, TimeoutError):
        return _result(current, "unreachable", "Could not reach GitHub. Check your internet connection.")
    except (ValueError, KeyError, TypeError):
        return _result(current, "error", "GitHub sent a response this version could not understand.")
