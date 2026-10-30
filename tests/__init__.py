"""Tests never touch the real config folder: everything goes to one throwaway directory."""
import atexit
import os
import shutil
import tempfile
import webbrowser

_cfg = tempfile.mkdtemp(prefix="modmanager-test-cfg-")
os.environ["MODMANAGER_CONFIG_DIR"] = _cfg
atexit.register(shutil.rmtree, _cfg, ignore_errors=True)
os.environ["MODMANAGER_LOG_DIR"] = _cfg
os.environ["MODMANAGER_FOLLOW_UP"] = "0"   # no timers that look at the game files later

# Never open a real link: on a PC with Steam, a test that presses Play on a fake game would otherwise send
# steam://run/<app id> to the real Steam client and start the real game's launcher. Tests that check the URL patch
# webbrowser.open themselves; everything else lands here.
OPENED = []


def _no_browser(url, *a, **k):
    OPENED.append(url)
    return True


webbrowser.open = webbrowser.open_new = webbrowser.open_new_tab = _no_browser
