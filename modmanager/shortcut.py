"""A desktop shortcut that starts this copy of the app (Windows only).

Asked about once at start-up (and offered in Settings > App & updates). The shortcut is written by Windows' own
WScript.Shell through PowerShell; the paths go in through environment variables, never into the command text.
"""
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

NAME = "Ronin Mod Manager.lnk"
ICON = Path(__file__).resolve().parent / "icon.ico"   # the app's own icon (same as the installer's)

_PS = ("$s = (New-Object -ComObject WScript.Shell).CreateShortcut($env:RMM_LNK); $s.TargetPath = $env:RMM_EXE; "
       "$s.Arguments = $env:RMM_ARGS; $s.WorkingDirectory = $env:RMM_DIR; $s.IconLocation = $env:RMM_ICON; "
       "$s.Description = $env:RMM_DESC; $s.Save()")
DESCRIPTION = "Ronin Mod Manager: mods and playsets for your games"
_SAFE = re.compile(r'[<>:"/\\|?*\x00-\x1f]+')


def supported():
    return sys.platform == "win32"


def desktop():
    """The user's Desktop folder (OneDrive moves it; Windows knows where). MODMANAGER_DESKTOP_DIR overrides it (tests)."""
    if os.environ.get("MODMANAGER_DESKTOP_DIR"):
        return Path(os.environ["MODMANAGER_DESKTOP_DIR"])
    if supported():
        try:
            import ctypes
            buf = ctypes.create_unicode_buffer(260)
            if ctypes.windll.shell32.SHGetFolderPathW(None, 0x10, None, 0, buf) == 0:   # CSIDL_DESKTOPDIRECTORY
                return Path(buf.value)
        except Exception:
            pass
    return Path.home() / "Desktop"


def path():
    return desktop() / NAME


def exists():
    return path().is_file()


def _windowless(exe):
    """pythonw.exe next to python.exe: the app opens its own window, so no console window should stay open."""
    p = Path(exe)
    if p.name.lower() == "python.exe" and (p.parent / "pythonw.exe").is_file():
        return p.parent / "pythonw.exe"
    return p


def target(cfg):
    """(program, arguments, start folder, icon) for this copy: the installed exe, the .pyzw file, or the source folder."""
    if getattr(sys, "frozen", False):
        exe = Path(sys.executable)
        return str(exe), "", str(exe.parent), f"{exe},0"
    icon = Path(cfg) / "icon.ico"   # a copy outside the app's files, which move to a new folder with every update
    try:
        icon.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ICON, icon)
    except OSError:
        icon = ICON
    exe = _windowless(sys.executable)
    pyz = os.environ.get("MODMANAGER_PYZ")
    if pyz:
        return str(exe), f'"{pyz}"', str(Path(pyz).parent), f"{icon},0"
    src = Path(__file__).resolve().parent.parent
    return str(exe), "-m modmanager", str(src), f"{icon},0"


def play_args(game_id, playset_id):
    """The arguments that start a game with one playset (`--game <id> --play <playset id>`); both are plain ids."""
    if not re.fullmatch(r"[a-z0-9][a-z0-9-]{0,40}", game_id) or not re.fullmatch(r"[A-Za-z0-9]{1,40}", playset_id):
        raise ValueError("Bad game or playset id.")
    return f"--game {game_id} --play {playset_id}"


def playset_name(game_name, playset_name):
    """'Crusader Kings III - My playset.lnk', with characters Windows does not allow in a file name left out."""
    text = re.sub(r"\s+", " ", _SAFE.sub(" ", f"{game_name} - {playset_name}")).strip(" .")[:80].rstrip(" .") or "Playset"
    return text + ".lnk"


def command(cfg, extra):
    """The command line a shortcut runs, as text (shown on systems where no shortcut file is made)."""
    exe, args, folder, _ = target(cfg)
    q = lambda s: f'"{s}"' if " " in s and not s.startswith('"') else s
    return " ".join(x for x in (q(exe), args, extra) if x)


def create(cfg, run=None, extra="", name=None, description=None):
    """Write a desktop shortcut (replacing one of the same name). `extra` adds arguments (a playset's shortcut). -> its path."""
    if not supported():
        raise ValueError("Desktop shortcuts are only made on Windows.")
    exe, args, folder, icon = target(cfg)
    args = " ".join(x for x in (args, extra) if x)
    lnk = desktop() / name if name else path()
    lnk.parent.mkdir(parents=True, exist_ok=True)
    env = dict(os.environ, RMM_LNK=str(lnk), RMM_EXE=exe, RMM_ARGS=args, RMM_DIR=folder, RMM_ICON=icon,
               RMM_DESC=description or DESCRIPTION)
    r = (run or subprocess.run)(["powershell", "-NoProfile", "-NonInteractive", "-Command", _PS], env=env,
                                capture_output=True, text=True, timeout=30, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    if r.returncode != 0 or not lnk.is_file():
        raise ValueError("Windows could not make the shortcut: " + ((r.stderr or r.stdout or "").strip().splitlines() or ["no reason given"])[-1][:200])
    return lnk
