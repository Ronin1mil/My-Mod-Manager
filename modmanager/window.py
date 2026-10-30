"""Show the app in its own window instead of a browser tab.

Backends, tried in order:
  1. pywebview: a native window around the system's web view (WebView2 on Windows, WebKit on macOS)
  2. the chromeless "app" window of an installed Edge / Chrome / Chromium
  3. nothing: the caller falls back to the default browser

show() blocks until the window is closed and returns "closed", "detached" (a window exists but this process
cannot tell when it closes) or None (no window could be opened).
"""
import os
import subprocess
import sys
import time
from pathlib import Path

from . import APP_NAME, errorlog
from .paths import config_dir

TITLE = APP_NAME
SIZE = (1320, 880)
MIN_SIZE = (940, 620)


def pywebview_module():
    """The webview module, or None when it is not installed or not wanted. Linux needs GTK or Qt bindings
    that cannot be assumed, so it uses the browser window instead."""
    if sys.platform.startswith("linux") or os.environ.get("MODMANAGER_NO_WEBVIEW"):
        return None
    try:
        import webview
        return webview
    except Exception:
        return None


def chromium_path():
    """Edge, Chrome or Chromium, whichever is installed (Edge first on Windows, where it always is)."""
    forced = os.environ.get("MODMANAGER_BROWSER_EXE")
    cands = [forced] if forced else []
    if sys.platform == "win32":
        roots = [os.environ.get(k) for k in ("ProgramFiles(x86)", "ProgramFiles", "LocalAppData")]
        for rel in ("Microsoft/Edge/Application/msedge.exe", "Google/Chrome/Application/chrome.exe"):
            cands += [Path(r) / rel for r in roots if r]
    elif sys.platform == "darwin":
        cands += ["/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
                  "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
                  "/Applications/Chromium.app/Contents/MacOS/Chromium"]
    else:
        import shutil
        cands += [shutil.which(n) for n in ("microsoft-edge", "google-chrome", "chromium", "chromium-browser")]
    for c in cands:
        if c and Path(c).is_file():
            return str(c)
    return None


def _native_ok():
    """Can pywebview load its platform layer here (WebView2 and .NET on Windows, WebKit on macOS)? -> (ok, error)"""
    if pywebview_module() is None:
        return False, "pywebview is not installed"
    try:
        if sys.platform == "win32":
            from webview.platforms import winforms  # noqa: F401
        elif sys.platform == "darwin":
            from webview.platforms import cocoa  # noqa: F401
        return True, ""
    except Exception as e:
        return False, f"{type(e).__name__}: {e}"


def probe():
    """What show() would use, without opening anything."""
    ok, err = _native_ok()
    return {"pywebview": pywebview_module() is not None, "native": ok, "native_error": err, "chromium": chromium_path(),
            "frozen": bool(getattr(sys, "frozen", False)), "platform": sys.platform}


def _run_pywebview(webview, url, title):
    try:
        webview.settings["ALLOW_DOWNLOADS"] = True  # exporting a playset saves a file
    except Exception:
        pass
    webview.create_window(title, url, width=SIZE[0], height=SIZE[1], min_size=MIN_SIZE)
    # On Windows insist on WebView2: the old Internet Explorer engine it could fall back to cannot draw this page.
    webview.start(gui="edgechromium" if sys.platform == "win32" else None)
    return "closed"


def _run_app_window(exe, url, title):
    profile = config_dir() / "window"
    profile.mkdir(parents=True, exist_ok=True)
    args = [exe, f"--app={url}", f"--user-data-dir={profile}", "--no-first-run", "--no-default-browser-check",
            "--disable-background-mode", f"--window-size={SIZE[0]},{SIZE[1]}"]
    started = time.time()
    subprocess.Popen(args, close_fds=True).wait()
    # a browser that was already running with this profile hands the window over and exits at once
    return "closed" if time.time() - started > 3 else "detached"


def uses_app_window():
    """True when show() would open a browser's app window (not a native one): a window that stays open after this process
    exits, so an update can find it still there."""
    return pywebview_module() is None and chromium_path() is not None


def show(url, title=TITLE, pywebview=None, chromium=None):
    wv = pywebview if pywebview is not None else pywebview_module()
    if wv:
        try:
            return _run_pywebview(wv, url, title)
        except Exception as e:
            errorlog.write_exception("window", e)
    exe = chromium if chromium is not None else chromium_path()
    if exe:
        try:
            return _run_app_window(exe, url, title)
        except Exception as e:
            errorlog.write_exception("window", e)
    return None


def message(title, text):
    """Tell the user something when there is no console to print it to (the Windows app has none)."""
    if sys.platform == "win32":
        try:
            import ctypes
            ctypes.windll.user32.MessageBoxW(None, str(text), str(title), 0x10)
        except Exception:
            pass
