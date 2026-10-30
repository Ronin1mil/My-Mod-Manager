"""Tests never touch the real config folder: everything goes to one throwaway directory."""
import atexit
import os
import shutil
import tempfile

_cfg = tempfile.mkdtemp(prefix="modmanager-test-cfg-")
os.environ["MODMANAGER_CONFIG_DIR"] = _cfg
atexit.register(shutil.rmtree, _cfg, ignore_errors=True)
os.environ["MODMANAGER_LOG_DIR"] = _cfg
os.environ["MODMANAGER_FOLLOW_UP"] = "0"   # no timers that look at the game files later
