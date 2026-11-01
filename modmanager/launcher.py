"""A stable start file for the Python edition (Windows only).

The .pyzw file can live anywhere (Downloads, a zip folder) and replaces itself when it updates. "Install on this PC"
copies the running .pyzw to %LOCALAPPDATA%\\Ronin Mod Manager\\app and writes "Ronin Mod Manager.bat" next to it. The
.bat always starts the copy beside it; with the "Install new versions when it starts" setting on, that copy installs a
newer release (checksum verified) before the window opens. Nothing is written outside that folder.
"""
import os
import shutil
import sys
from pathlib import Path

PYZ_NAME = "Mod-Manager-python.pyzw"
BAT_NAME = "Ronin Mod Manager.bat"

BAT = """@echo off
rem Starts Ronin Mod Manager. Safe to double-click; it can be moved, the app file next to it is what runs.
rem Python 3.8 or newer from python.org is needed (it brings the "py" and "pyw" launchers).
set "HERE=%~dp0"
where pyw >nul 2>nul && (start "" pyw "%HERE%{pyz}" --update-first %* & exit /b 0)
where pythonw >nul 2>nul && (start "" pythonw "%HERE%{pyz}" --update-first %* & exit /b 0)
where py >nul 2>nul && (py "%HERE%{pyz}" --update-first %* & exit /b 0)
echo Python was not found. Install Python 3.8 or newer from https://www.python.org/downloads/ and run this again.
pause
"""


def supported():
    return sys.platform == "win32"


def app_dir():
    """Where the installed copy lives. MODMANAGER_APP_DIR overrides it (tests)."""
    if os.environ.get("MODMANAGER_APP_DIR"):
        return Path(os.environ["MODMANAGER_APP_DIR"])
    base = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
    return Path(base) / "Ronin Mod Manager" / "app"


def bat_path():
    return app_dir() / BAT_NAME


def installed():
    return (app_dir() / PYZ_NAME).is_file() and bat_path().is_file()


def running_installed(pyz):
    """True when `pyz` is the installed copy already."""
    try:
        return pyz is not None and Path(pyz).resolve() == (app_dir() / PYZ_NAME).resolve()
    except OSError:
        return False


def install(pyz):
    """Copy the running .pyzw into the app folder and write the .bat. Returns the .bat's path."""
    if pyz is None or not Path(pyz).is_file():
        raise ValueError("This copy runs from source files, so there is no app file to install. Use the downloaded "
                         "Mod-Manager-python.pyzw.")
    d = app_dir()
    d.mkdir(parents=True, exist_ok=True)
    dest = d / PYZ_NAME
    if not running_installed(pyz):
        tmp = d / (PYZ_NAME + ".part")
        shutil.copyfile(pyz, tmp)
        os.replace(tmp, dest)
    bat_path().write_text(BAT.format(pyz=PYZ_NAME).replace("\n", "\r\n"), encoding="ascii")
    return bat_path()
