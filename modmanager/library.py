"""Persistent mod library: every mod ever seen, with change tracking between scans."""
import json
import time
import uuid
from pathlib import Path

from .paths import config_dir

CHANGE_VISIBLE_SECS = 7 * 24 * 3600


class Library:
    def __init__(self, path=None, game=None):
        self.path = Path(path) if path else config_dir(game) / "library.json"
        self.data = {"entries": {}, "scanned_once": False}
        try:
            d = json.loads(self.path.read_text())
            if isinstance(d, dict) and isinstance(d.get("entries"), dict):
                self.data = d
        except (OSError, ValueError):
            pass

    def save(self):
        tmp = self.path.with_suffix(f".{uuid.uuid4().hex[:8]}.tmp")
        tmp.write_text(json.dumps(self.data, indent=1))
        tmp.replace(self.path)

    def merge(self, mods, now=None):
        """Record a scan. Returns {total, added, updated, removed}. The very first scan marks nothing as new."""
        now = int(now if now is not None else time.time())
        first = not self.data.get("scanned_once")
        e, diff = self.data["entries"], {"total": len(mods), "added": 0, "updated": 0, "removed": 0}
        for mid, m in mods.items():
            cur = e.get(mid)
            if cur is None:
                e[mid] = {"name": m["name"], "version": m["version"], "present": True, "first_seen": now,
                          "last_seen": now, "change": "none" if first else "new", "changed_at": now}
                diff["added"] += 0 if first else 1
                continue
            if not cur["present"]:
                cur.update(change="new", changed_at=now)
                diff["added"] += 1
            elif cur["version"] != m["version"]:
                cur.update(change="updated", changed_at=now, previous_version=cur["version"])
                diff["updated"] += 1
            cur.update(name=m["name"], version=m["version"], present=True, last_seen=now)
        for mid, cur in e.items():
            if mid not in mods and cur["present"]:
                cur.update(present=False, change="removed", changed_at=now)
                diff["removed"] += 1
        self.data["scanned_once"] = True
        self.save()
        return diff

    def change(self, mid, now=None):
        """Badge to show now: 'new' | 'updated' | 'none' (fades after a week)."""
        cur = self.data["entries"].get(mid)
        now = int(now if now is not None else time.time())
        if not cur or cur["change"] in ("none", "removed") or now - cur["changed_at"] > CHANGE_VISIBLE_SECS:
            return "none"
        return cur["change"]

    def removed(self):
        return [{"id": k, "name": v["name"]} for k, v in self.data["entries"].items() if not v["present"]]
