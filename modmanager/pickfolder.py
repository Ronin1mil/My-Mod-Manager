"""Ask the user for a folder with the system's own "choose a folder" window.

The app runs as a local server, so the window has to be opened by a program on this PC, not by the web page (a web page
is never told where a folder is on the disk). On Windows this is PowerShell's folder window (always installed); elsewhere
(and if PowerShell is missing) Python's tkinter, when it is there. If neither can open a window the answer says so and the
page falls back to pasting the path.

The title and the starting folder are passed in environment variables, never put into the script text, so nothing the page
sends can become code. Nothing is searched or read here: the user chooses, and the caller then looks only at that folder.
"""
import os
import shutil
import subprocess
import sys
from pathlib import Path

NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)
WAIT = 900   # seconds the user has to choose

# An invisible top-most owner window makes the dialog open in front of the app's window instead of behind it.
POWERSHELL = r"""
Add-Type -AssemblyName System.Windows.Forms
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$o = New-Object System.Windows.Forms.Form
$o.TopMost = $true
$d = New-Object System.Windows.Forms.FolderBrowserDialog
$d.Description = $env:RMM_PICK_TITLE
$d.ShowNewFolderButton = $false
if ($env:RMM_PICK_START -and (Test-Path -LiteralPath $env:RMM_PICK_START -PathType Container)) { $d.SelectedPath = $env:RMM_PICK_START }
if ($d.ShowDialog($o) -eq [System.Windows.Forms.DialogResult]::OK) { [Console]::Out.Write($d.SelectedPath) }
"""

TKINTER = r"""
import os, tkinter
from tkinter import filedialog
r = tkinter.Tk(); r.withdraw(); r.attributes("-topmost", True)
p = filedialog.askdirectory(title=os.environ.get("RMM_PICK_TITLE") or "Choose a folder", initialdir=os.environ.get("RMM_PICK_START") or None, parent=r)
print(p or "", end="")
"""


def _powershell():
    if os.name != "nt":
        return None
    root = os.environ.get("SystemRoot") or r"C:\Windows"
    p = Path(root) / "System32" / "WindowsPowerShell" / "v1.0" / "powershell.exe"
    return str(p) if p.is_file() else shutil.which("powershell")


def pick_folder(title="Choose a folder", start="", runner=subprocess.run):
    """-> {"path": the chosen folder or "", "cancelled": bool, "error": text}. Waits until the user chooses or cancels."""
    start = str(start or "")
    env = {**os.environ, "RMM_PICK_TITLE": str(title)[:200], "RMM_PICK_START": start if start and Path(start).is_dir() else ""}
    ps = _powershell()
    argv = [ps, "-NoProfile", "-NonInteractive", "-STA", "-Command", POWERSHELL] if ps else [sys.executable, "-c", TKINTER]
    try:
        r = runner(argv, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=WAIT, env=env,
                   stdin=subprocess.DEVNULL, creationflags=NO_WINDOW)
    except subprocess.TimeoutExpired:
        return {"path": "", "cancelled": True, "error": ""}
    except (OSError, subprocess.SubprocessError) as e:
        return {"path": "", "cancelled": False, "error": f"The folder window could not be opened ({type(e).__name__}). Paste the folder's path instead."}
    path = (r.stdout or "").strip()
    if path and Path(path).is_dir():
        return {"path": path, "cancelled": False, "error": ""}
    if r.returncode != 0 and not path:   # no window program here (for example Python without tkinter)
        return {"path": "", "cancelled": False, "error": "This PC could not open a folder window. Paste the folder's path instead."}
    return {"path": "", "cancelled": True, "error": ""}   # the user pressed Cancel
