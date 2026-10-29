"""Starting the game. Never builds a shell string: the game is spawned from an argument list, or
started through a steam:// URL whose arguments are percent-encoded."""
import re
import subprocess
import urllib.parse
import webbrowser
from pathlib import Path


MAX_ARGS = 8
ARG_OK = re.compile(r"^[-/][A-Za-z0-9_.:/=\-]{1,63}$")


def validate_launch_args(args):
    if not isinstance(args, list) or not all(isinstance(a, str) for a in args):
        raise ValueError("Launch arguments must be a list of text values.")
    out = [a.strip() for a in args if a.strip()]
    if len(out) > MAX_ARGS:
        raise ValueError(f"At most {MAX_ARGS} extra launch arguments are allowed.")
    for a in out:
        if not ARG_OK.match(a) or not any(c.isalnum() for c in a[1:]):
            raise ValueError(f"'{a}' is not an allowed launch argument. Use flags like -debug_mode "
                             "(letters, digits and _ . / : = - only, up to 64 characters).")
        if a.lower().startswith(("-applaunch", "-exec")):
            raise ValueError(f"'{a}' is controlled by the manager and can't be set here.")
    return out


def steam_url(game, args):
    base = f"steam://run/{game.app_id}"
    if not args:
        return base
    return f"{base}//{urllib.parse.quote(' '.join(args), safe='-_.=:/')}/"


def start(game, game_exe, args):
    """Spawn the game directly when an executable is configured, otherwise go through Steam."""
    if game_exe:
        exe = Path(game_exe)
        if not exe.is_file():
            raise ValueError(f"Game executable not found: {exe}")
        subprocess.Popen([str(exe), *args], cwd=str(exe.parent), close_fds=True)
        return {"via": "exe"}
    webbrowser.open(steam_url(game, args))
    return {"via": "steam"}
