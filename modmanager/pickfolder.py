"""Ask the user for a folder with the system's own "choose a folder" window.

The app runs as a local server, so the window has to be opened by a program on this PC, not by the web page (a web page
is never told where a folder is on the disk). On Windows this is PowerShell opening the Explorer-style folder window (always installed); elsewhere
(and if PowerShell is missing) Python's tkinter, when it is there. If neither can open a window the answer says so and the
page falls back to pasting the path.

The title and the starting folder are passed in environment variables, never put into the script text, so nothing the page
sends can become code. Nothing is searched or read here: the user chooses, and the caller then looks only at that folder.
"""
import base64
import os
import shutil
import subprocess
import sys
from pathlib import Path

NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)
WAIT = 900   # seconds the user has to choose

# Windows has two folder windows. The old one (FolderBrowserDialog) is a small tree of folders. The current one is the same
# window as File Explorer's Open window, in "choose a folder" mode (IFileOpenDialog with FOS_PICKFOLDERS): address bar, search,
# Quick access, This PC. This uses the current one, and falls back to the old one only if it cannot be built on this PC.
# An invisible top-most owner window makes the dialog open in front of the app's window instead of behind it.
CSHARP = r"""
using System;
using System.Runtime.InteropServices;
[ComImport, Guid("DC1C5A9C-E88A-4DDE-A5A1-60F82A20AEF7")] public class RmmFileOpenDialog { }
[ComImport, Guid("43826D1E-E718-42EE-BC55-A1E261C37BFE"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
public interface IRmmShellItem {
    void BindToHandler(IntPtr pbc, ref Guid bhid, ref Guid riid, out IntPtr ppv);
    void GetParent(out IRmmShellItem ppsi);
    void GetDisplayName(uint sigdnName, [MarshalAs(UnmanagedType.LPWStr)] out string name);
    void GetAttributes(uint mask, out uint attr);
    void Compare(IRmmShellItem psi, uint hint, out int order);
}
[ComImport, Guid("42F85136-DB7E-439C-85F1-E4075D135FC8"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
public interface IRmmFileDialog {
    [PreserveSig] int Show(IntPtr parent);
    void SetFileTypes(uint count, IntPtr types);
    void SetFileTypeIndex(uint index);
    void GetFileTypeIndex(out uint index);
    void Advise(IntPtr events, out uint cookie);
    void Unadvise(uint cookie);
    void SetOptions(uint options);
    void GetOptions(out uint options);
    void SetDefaultFolder(IRmmShellItem item);
    void SetFolder(IRmmShellItem item);
    void GetFolder(out IRmmShellItem item);
    void GetCurrentSelection(out IRmmShellItem item);
    void SetFileName([MarshalAs(UnmanagedType.LPWStr)] string name);
    void GetFileName([MarshalAs(UnmanagedType.LPWStr)] out string name);
    void SetTitle([MarshalAs(UnmanagedType.LPWStr)] string title);
    void SetOkButtonLabel([MarshalAs(UnmanagedType.LPWStr)] string text);
    void SetFileNameLabel([MarshalAs(UnmanagedType.LPWStr)] string text);
    void GetResult(out IRmmShellItem item);
}
public static class RmmFolder {
    [DllImport("shell32.dll", CharSet = CharSet.Unicode)]
    static extern int SHCreateItemFromParsingName(string path, IntPtr bindContext, ref Guid riid, out IRmmShellItem item);
    public static string Pick(IntPtr owner, string title, string start) {
        IRmmFileDialog dlg = (IRmmFileDialog)new RmmFileOpenDialog();
        uint options; dlg.GetOptions(out options);
        dlg.SetOptions(options | 0x20 | 0x40 | 0x800);   // pick folders, real folders only, the path must exist
        if (!string.IsNullOrEmpty(title)) dlg.SetTitle(title);
        if (!string.IsNullOrEmpty(start)) {
            Guid iid = new Guid("43826D1E-E718-42EE-BC55-A1E261C37BFE"); IRmmShellItem folder;
            if (SHCreateItemFromParsingName(start, IntPtr.Zero, ref iid, out folder) == 0) dlg.SetFolder(folder);
        }
        int hr = dlg.Show(owner);
        if (hr == unchecked((int)0x800704C7)) return "";   // Cancel
        if (hr != 0) throw new COMException("The folder window failed", hr);
        IRmmShellItem item; dlg.GetResult(out item);
        string path; item.GetDisplayName(0x80058000, out path);   // SIGDN_FILESYSPATH
        return path;
    }
}
"""

POWERSHELL = r"""
$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Windows.Forms
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$o = New-Object System.Windows.Forms.Form
$o.TopMost = $true; $o.ShowInTaskbar = $false; $o.Opacity = 0; $o.Show()
$start = ''
if ($env:RMM_PICK_START -and (Test-Path -LiteralPath $env:RMM_PICK_START -PathType Container)) { $start = $env:RMM_PICK_START }
if ($env:RMM_PICK_KIND -eq 'file') {   # a file, not a folder (a .rnworld map file): Explorer's own Open window
  $f = New-Object System.Windows.Forms.OpenFileDialog
  $f.Title = $env:RMM_PICK_TITLE
  $f.Filter = 'Random New World map (*.rnworld)|*.rnworld|All files (*.*)|*.*'
  if ($start) { $f.InitialDirectory = $start }
  if ($f.ShowDialog($o) -eq [System.Windows.Forms.DialogResult]::OK) { [Console]::Out.Write($f.FileName) }
  exit 0
}
$modern = $false; $path = ''
try {
  Add-Type -TypeDefinition @'
__CSHARP__
'@
  $path = [RmmFolder]::Pick($o.Handle, $env:RMM_PICK_TITLE, $start)
  $modern = $true
} catch { $modern = $false }
if (-not $modern) {
  $d = New-Object System.Windows.Forms.FolderBrowserDialog
  $d.Description = $env:RMM_PICK_TITLE
  $d.ShowNewFolderButton = $false
  if ($start) { $d.SelectedPath = $start }
  if ($d.ShowDialog($o) -eq [System.Windows.Forms.DialogResult]::OK) { $path = $d.SelectedPath }
}
if ($path) { [Console]::Out.Write($path) }
""".replace("__CSHARP__", CSHARP.strip("\n"))

TKINTER = r"""
import os, tkinter
from tkinter import filedialog
r = tkinter.Tk(); r.withdraw(); r.attributes("-topmost", True)
title, start = os.environ.get("RMM_PICK_TITLE") or "Choose", os.environ.get("RMM_PICK_START") or None
if os.environ.get("RMM_PICK_KIND") == "file":
    p = filedialog.askopenfilename(title=title, initialdir=start, parent=r, filetypes=[("Random New World map", "*.rnworld"), ("All files", "*")])
else:
    p = filedialog.askdirectory(title=title, initialdir=start, parent=r)
print(p or "", end="")
"""


def _powershell():
    if os.name != "nt":
        return None
    root = os.environ.get("SystemRoot") or r"C:\Windows"
    p = Path(root) / "System32" / "WindowsPowerShell" / "v1.0" / "powershell.exe"
    return str(p) if p.is_file() else shutil.which("powershell")


def pick_folder(title="Choose a folder", start="", runner=subprocess.run, kind="folder"):
    """-> {"path": the chosen folder (kind="file": file) or "", "cancelled": bool, "error": text}. Waits until the user chooses or cancels."""
    kind = "file" if kind == "file" else "folder"
    start = str(start or "")
    start_dir = str(Path(start).parent) if kind == "file" and start and Path(start).is_file() else start
    env = {**os.environ, "RMM_PICK_TITLE": str(title)[:200], "RMM_PICK_START": start_dir if start_dir and Path(start_dir).is_dir() else "", "RMM_PICK_KIND": kind}
    ps = _powershell()
    # the script goes in as base64 (-EncodedCommand): no quoting of the C# text on the command line can go wrong
    argv = [ps, "-NoProfile", "-NonInteractive", "-STA", "-EncodedCommand", base64.b64encode(POWERSHELL.encode("utf-16-le")).decode("ascii")] if ps else [sys.executable, "-c", TKINTER]
    try:
        r = runner(argv, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=WAIT, env=env,
                   stdin=subprocess.DEVNULL, creationflags=NO_WINDOW)
    except subprocess.TimeoutExpired:
        return {"path": "", "cancelled": True, "error": ""}
    except (OSError, subprocess.SubprocessError) as e:
        return {"path": "", "cancelled": False, "error": f"The folder window could not be opened ({type(e).__name__}). Paste the folder's path instead."}
    path = (r.stdout or "").strip()
    if path and (Path(path).is_file() if kind == "file" else Path(path).is_dir()):
        return {"path": path, "cancelled": False, "error": ""}
    if r.returncode != 0 and not path:   # no window program here (for example Python without tkinter)
        return {"path": "", "cancelled": False, "error": "This PC could not open a folder window. Paste the folder's path instead."}
    return {"path": "", "cancelled": True, "error": ""}   # the user pressed Cancel
