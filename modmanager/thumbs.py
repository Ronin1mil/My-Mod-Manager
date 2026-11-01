"""A mod's own picture, for the cards and rows in the app. Read from the mod's folder only, never from the network.

Paradox mods ship `thumbnail.png` (in the mod folder, or in `.metadata/`); some mods use `preview.*` or `cover.*`.
The file must be a real image file inside the mod's own folder (links are not followed), of a known type and not huge.
"""
import os
import stat
from pathlib import Path

TYPES = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".webp": "image/webp", ".gif": "image/gif"}
MAX_BYTES = 3 * 1024 * 1024
NAMES = ("thumbnail", "preview", "cover", "icon")
FOLDERS = ("", ".metadata", "metadata")


def find(root):
    """-> Path of the mod's picture, or None. Looks in the mod folder, then `.metadata` and `metadata`, for
    thumbnail / preview / cover / icon with a png, jpg, jpeg, webp or gif extension."""
    if not root:
        return None
    base = Path(root)
    for sub in FOLDERS:
        for name in NAMES:
            for ext in TYPES:
                p = base / sub / (name + ext) if sub else base / (name + ext)
                try:
                    st = os.lstat(p)
                except OSError:
                    continue
                if stat.S_ISREG(st.st_mode) and 0 < st.st_size <= MAX_BYTES:
                    return p
    return None
