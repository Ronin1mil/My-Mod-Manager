"""Find a game's Steam install and its matching Workshop folder (any library, any drive).

An install is recognised by `Game.install_marker` (e.g. game/in_game), so a user can paste any path
inside it and it resolves to the install root.
"""
import re
from pathlib import Path

from .paths import game_version, steam_libraries


def marker_ok(root, game):
    try:
        return (Path(root).joinpath(*game.install_marker)).is_dir()
    except OSError:
        return False


def find_install_root(p, game):
    """Resolve any path inside an install (root, game/, game/in_game/common/x, ...) to the root, or None."""
    if not p or not str(p).strip():
        return None
    p = Path(p)
    for c in [p, *list(p.parents)[:10]]:
        if marker_ok(c, game):
            return c
        # the marker is "<root>/game/<x>": a path at or below game/ also resolves
        if c.name.lower() == game.install_marker[0] and marker_ok(c.parent, game):
            return c.parent
    return None


def workshop_dir_for(root, game):
    """Workshop content folder in the same Steam library as the install, if it exists."""
    root = Path(root)
    if root.parent.name.lower() != "common":
        return None
    d = root.parent.parent / "workshop" / "content" / game.app_id
    return d if d.is_dir() else None


def describe(root, game):
    root = Path(root)
    ws = workshop_dir_for(root, game)
    return {"path": str(root), "game_dir": str(root / game.vanilla_dir_name), "version": game_version(root),
            "workshop_dir": str(ws) if ws else "",
            "store": "steam" if "steamapps" in str(root).lower() else "manual"}


def _installdir(lib, game):
    """Folder name from Steam's appmanifest (handles renamed installs); falls back to the default."""
    try:
        t = (lib / "steamapps" / f"appmanifest_{game.app_id}.acf").read_text(errors="replace")
        m = re.search(r'"installdir"\s+"([^"]+)"', t)
        if m:
            return m.group(1)
    except OSError:
        pass
    return game.install_dir_name


def detect_all(game, extra_libraries=()):
    """All installs of `game` found on this machine: [describe(...)]."""
    out, seen = [], set()
    for lib in steam_libraries(extra_libraries):
        root = find_install_root(lib / "steamapps" / "common" / _installdir(lib, game), game)
        if root and str(root).lower() not in seen:
            seen.add(str(root).lower())
            out.append(describe(root, game))
    return out
