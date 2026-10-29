"""Per-mod update tracking for Workshop mods.

Local truth: Steam's own record of when it last downloaded each item (steamapps/workshop/appworkshop_<app>.acf).
Remote truth: the item's `time_updated` from Steam's public Web API. If remote is newer, an update exists.
Runs only when the user presses "Check mod updates". Nothing is downloaded.
"""
import re
from pathlib import Path

from .collections import default_post

TOKEN = re.compile(r'"((?:[^"\\]|\\.)*)"|([{}])')


def parse_vdf(text):
    """Minimal Valve KeyValues parser -> nested dicts (values are strings)."""
    stack, key, cur = [], None, {}
    root = cur
    for m in TOKEN.finditer(text):
        s, brace = m.group(1), m.group(2)
        if brace == "{":
            if key is None:
                raise ValueError("bad vdf")
            child = {}
            cur[key] = child
            stack.append(cur)
            cur, key = child, None
        elif brace == "}":
            if not stack:
                raise ValueError("bad vdf")
            cur, key = stack.pop(), None
        elif key is None:
            key = s
        else:
            cur[key] = s
            key = None
    if stack:
        raise ValueError("bad vdf")
    return root


def local_times(workshop_dir, app_id):
    """{workshop id: unix time Steam last updated it locally}. Empty when the record is missing."""
    if not workshop_dir:
        return {}
    acf = Path(workshop_dir).parent.parent / f"appworkshop_{app_id}.acf"
    try:
        d = parse_vdf(acf.read_text(encoding="utf-8", errors="replace"))
        items = next(iter(d.values()))["WorkshopItemsInstalled"]
    except (OSError, ValueError, KeyError, StopIteration, TypeError):
        return {}
    out = {}
    for wid, v in items.items():
        try:
            out[str(wid)] = int(v["timeupdated"])
        except (KeyError, ValueError, TypeError):
            pass
    return out


def check(mods, workshop_dir, app_id, post=default_post):
    """[{id, name, remote_id, status: update|current|unknown, local, remote}] for the Workshop mods."""
    ws = [m for m in mods.values() if m.get("source") == "workshop" or str(m.get("id", "")).startswith("ws:")]
    ids = [str(m["remote_id"]) for m in ws if m.get("remote_id") and re.fullmatch(r"\d{1,20}", str(m["remote_id"]))]
    local, remote = local_times(workshop_dir, app_id), {}
    for i in range(0, len(ids), 100):
        batch = ids[i:i + 100]
        fields = {"itemcount": len(batch), **{f"publishedfileids[{n}]": w for n, w in enumerate(batch)}}
        resp = post("/ISteamRemoteStorage/GetPublishedFileDetails/v1/", fields)
        try:
            for d in resp["response"]["publishedfiledetails"]:
                if d.get("result") == 1:
                    remote[str(d["publishedfileid"])] = int(d["time_updated"])
        except (KeyError, TypeError, ValueError):
            raise ValueError("Steam's answer was not understood.")
    out = []
    for m in ws:
        rid = str(m.get("remote_id") or "")
        l, r = local.get(rid), remote.get(rid)
        status = "unknown" if l is None or r is None else "update" if r > l else "current"
        out.append({"id": m["id"], "name": m["name"], "remote_id": rid, "status": status, "local": l, "remote": r})
    return sorted(out, key=lambda x: ({"update": 0, "unknown": 1, "current": 2}[x["status"]], x["name"].lower()))
