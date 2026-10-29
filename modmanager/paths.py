"""Where things live: config folders, user data, Steam libraries, logos. Everything takes a Game."""
import json
import os
import re
import sys
from pathlib import Path

_VDF_PATH = re.compile(r'"path"\s+"([^"]+)"')
_VERSION = re.compile(r"\d+(?:\.\d+)+")


def config_dir(game=None):
    """App config folder; with a game, that game's own subfolder (playsets, library, saves, backups).
    MODMANAGER_CONFIG_DIR overrides the location (tests, portable installs)."""
    base = os.environ.get("MODMANAGER_CONFIG_DIR")
    if not base:
        base = os.environ.get("XDG_CONFIG_HOME") or (
            os.environ.get("APPDATA") if sys.platform == "win32" else str(Path.home() / ".config"))
        base = str(Path(base) / "modmanager")
    d = Path(base) / game.id if game else Path(base)
    d.mkdir(parents=True, exist_ok=True)
    return d


def legacy_config_files(game):
    """Playset files written by the standalone managers this app replaces (migrated on first start)."""
    base = os.environ.get("XDG_CONFIG_HOME") or (
        os.environ.get("APPDATA") if sys.platform == "win32" else str(Path.home() / ".config"))
    return [Path(base) / n / "playsets.json" for n in game.legacy_config]


def user_dirs(game):
    home = Path.home()
    rel = Path("Paradox Interactive") / game.user_dir_name
    c = [home / "Documents" / rel, home / ".local/share" / rel, home / "Library/Application Support" / rel,
         home / "OneDrive/Documents" / rel]
    if sys.platform == "win32":
        up = os.environ.get("USERPROFILE")
        if up:
            c.insert(0, Path(up) / "Documents" / rel)
    return c


def steam_roots():
    home = Path.home()
    return [Path("C:/Program Files (x86)/Steam"), Path("C:/Program Files/Steam"), home / ".steam/steam",
            home / ".local/share/Steam", home / "Library/Application Support/Steam"]


def registry_steam_roots():
    if sys.platform != "win32":
        return []
    import winreg
    out = []
    for hive, sub, name in ((winreg.HKEY_CURRENT_USER, r"Software\Valve\Steam", "SteamPath"),
                            (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\Valve\Steam", "InstallPath")):
        try:
            with winreg.OpenKey(hive, sub) as k:
                out.append(Path(winreg.QueryValueEx(k, name)[0]))
        except OSError:
            pass
    return out


def parse_library_folders_vdf(text):
    return [Path(m.replace("\\\\", "\\")) for m in _VDF_PATH.findall(text)]


def drive_guesses():
    """Libraries people create by hand on other drives, e.g. G:/SteamLibrary (Windows only)."""
    if sys.platform != "win32":
        return []
    names = ("SteamLibrary", "Steam", "Games/Steam", "Games/SteamLibrary", "Program Files (x86)/Steam")
    return [Path(f"{d}:/") / n for d in "CDEFGHIJKLMNOPQRSTUVWXYZ" for n in names if Path(f"{d}:/").exists()]


def steam_libraries(extra=()):
    """Every Steam library root we can discover (those with a steamapps folder), de-duplicated."""
    roots = [Path(p) for p in extra] + registry_steam_roots() + steam_roots()
    libs = list(roots)
    for r in roots:
        try:
            libs += parse_library_folders_vdf((r / "steamapps" / "libraryfolders.vdf").read_text(errors="replace"))
        except OSError:
            pass
    libs += drive_guesses()
    seen, out = set(), []
    for lib in libs:
        k = str(lib).rstrip("/\\").lower()
        if k not in seen and (lib / "steamapps").is_dir():
            seen.add(k)
            out.append(lib)
    return out


def workshop_dirs(game, extra=()):
    return [lib / "steamapps/workshop/content" / game.app_id for lib in steam_libraries(extra)]


def find_first(cands):
    return next((p for p in cands if p.is_dir()), None)


def game_version(root):
    """Installed game version (e.g. '1.7.6') from launcher/launcher-settings.json; '' when unknown."""
    if not root:
        return ""
    try:
        d = json.loads((Path(root) / "launcher" / "launcher-settings.json").read_text(encoding="utf-8-sig"))
    except (OSError, ValueError):
        return ""
    if not isinstance(d, dict):
        return ""
    for key in ("rawVersion", "version"):
        m = _VERSION.search(str(d.get(key, "")))
        if m:
            return m.group(0)
    return ""


# ---- logos: never bundled; the user's own Steam cache, a file they provide, or an explicit download ----
LOGO_TYPES = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".webp": "image/webp",
              ".svg": "image/svg+xml"}
MAX_LOGO = 2 * 1024 * 1024


def logo_url(game):
    return f"https://shared.fastly.steamstatic.com/store_item_assets/steam/apps/{game.app_id}/logo.png"


def steam_cache_logo(game, extra=()):
    for root in [Path(p) for p in extra] + registry_steam_roots() + steam_roots():
        cache = root / "appcache/librarycache"
        for p in [cache / f"{game.app_id}_logo.png", *sorted((cache / game.app_id).glob("**/logo.png"))]:
            if p.is_file() and p.stat().st_size <= MAX_LOGO:
                return p
    return None


def find_logo(game, explicit=None, game_root=None, extra=()):
    """--logo, else logo.<ext> in the game's config folder, else Steam's local library cache,
    else a *logo*.png in the install's launcher folder."""
    cands = [Path(explicit)] if explicit else [config_dir(game) / f"logo{e}" for e in LOGO_TYPES]
    for p in cands:
        if p.suffix.lower() in LOGO_TYPES and p.is_file() and p.stat().st_size <= MAX_LOGO:
            return p
    if explicit:
        return None
    hit = steam_cache_logo(game, extra)
    if hit or not game_root:
        return hit
    for p in sorted((Path(game_root) / "launcher").glob("*logo*.png")):
        if p.is_file() and p.stat().st_size <= MAX_LOGO:
            return p
    return None


def fetch_logo(game, url=None):
    """Explicit, user-requested download of the game's logo from Steam's CDN into the config folder.
    HTTPS only, fixed host suffix, size-capped, must be a real PNG. Returns the saved path."""
    import urllib.request
    from urllib.parse import urlparse
    url = url or logo_url(game)
    u = urlparse(url)
    if u.scheme != "https" or not (u.hostname or "").endswith(".steamstatic.com"):
        raise ValueError("Logo downloads are limited to https://*.steamstatic.com")
    with urllib.request.urlopen(url, timeout=20) as r:
        data = r.read(MAX_LOGO + 1)
    if len(data) > MAX_LOGO or not data.startswith(b"\x89PNG\r\n\x1a\n"):
        raise ValueError("Downloaded file is not a valid PNG logo.")
    dest = config_dir(game) / "logo.png"
    dest.write_bytes(data)
    return dest
