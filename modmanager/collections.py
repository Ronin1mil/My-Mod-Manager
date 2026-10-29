"""Turn a Steam Workshop collection into a preset.

Started only by the user pasting a link and pressing Import. One keyless request to Steam's public
Web API (api.steampowered.com, https only) lists the collection's items and a second fetches their
titles. Nothing is installed or downloaded; the result is an ordinary preset.
"""
import json
import re
import urllib.error
import urllib.parse
import urllib.request

from . import presets

HOST = "api.steampowered.com"
MAX_BYTES = 2 * 1024 * 1024
URL_RE = re.compile(r"^https?://steamcommunity\.com/(?:sharedfiles|workshop)/filedetails/?\?(?:.*&)?id=(\d{1,20})(?:&.*)?$")


def parse_collection_id(text):
    """Collection id from a Workshop link or a bare number."""
    t = str(text or "").strip()
    if re.fullmatch(r"\d{1,20}", t):
        return t
    m = URL_RE.match(t)
    if not m:
        raise ValueError("Paste a Steam Workshop collection link (steamcommunity.com/sharedfiles/filedetails/?id=...) or its number.")
    return m.group(1)


def default_post(path, fields, timeout=15):
    url = f"https://{HOST}{path}"
    data = urllib.parse.urlencode(fields).encode()
    req = urllib.request.Request(url, data=data, headers={"User-Agent": "modmanager-collection-import"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            raw = r.read(MAX_BYTES + 1)
    except urllib.error.HTTPError as e:
        raise ValueError(f"Steam answered with an error ({e.code}).")
    except (urllib.error.URLError, OSError) as e:
        raise ValueError(f"Could not reach Steam: {getattr(e, 'reason', e)}")
    if len(raw) > MAX_BYTES:
        raise ValueError("Steam's answer was too large.")
    try:
        return json.loads(raw.decode("utf-8", "replace"))
    except ValueError:
        raise ValueError("Steam's answer was not understood.")


def _slug(text, fallback):
    s = re.sub(r"[^a-z0-9]+", "-", str(text).lower()).strip("-")[:50]
    return s or fallback


def import_collection(game, text, post=default_post):
    """Return a preset document for the collection (not yet saved)."""
    cid = parse_collection_id(text)
    resp = post("/ISteamRemoteStorage/GetCollectionDetails/v1/", {"collectioncount": 1, "publishedfileids[0]": cid})
    try:
        det = resp["response"]["collectiondetails"][0]
        if det.get("result") != 1:
            raise KeyError
        children = det.get("children") or []
    except (KeyError, IndexError, TypeError):
        raise ValueError("Steam does not know that collection. Is the link a collection (not a single mod) and is it public?")
    items = sorted((c for c in children if isinstance(c, dict) and re.fullmatch(r"\d{1,20}", str(c.get("publishedfileid", "")))),
                   key=lambda c: c.get("sortorder", 0) if isinstance(c.get("sortorder", 0), int) else 0)
    ids = list(dict.fromkeys(str(c["publishedfileid"]) for c in items))
    if not ids:
        raise ValueError("That collection has no mods in it.")
    ids = ids[:presets.MAX_MODS]
    names, title, note, gone, other_game = {}, None, "", set(), False
    fields = {"itemcount": len(ids) + 1, "publishedfileids[0]": cid}
    fields.update({f"publishedfileids[{i + 1}]": w for i, w in enumerate(ids)})
    try:
        for d in post("/ISteamRemoteStorage/GetPublishedFileDetails/v1/", fields)["response"]["publishedfiledetails"]:
            wid, app = str(d.get("publishedfileid")), str(d.get("consumer_app_id") or "")
            if wid == cid:
                title, note = d.get("title"), d.get("description", "")
                other_game = bool(app) and app != str(game.app_id)
            elif d.get("result") not in (None, 1):
                gone.add(wid)  # deleted or hidden on Steam: it could never be downloaded
            elif d.get("title"):
                names[wid] = str(d["title"])[:120]
    except (KeyError, TypeError, ValueError):
        pass  # names are a nicety; ids alone make a working preset
    if other_game:
        raise ValueError(f"That collection is for another game, not {game.name}. Open that game and import it there.")
    ids = [w for w in ids if w not in gone]
    if not ids:
        raise ValueError("Every mod in that collection has been removed from Steam.")
    title = str(title or f"Collection {cid}")[:60]
    return {"format": presets.FORMAT, "id": _slug(title, f"collection-{cid}"), "game": game.id, "name": title,
            "status": "unverified",
            "description": ("Imported from Steam Workshop collection " + cid + ". " + str(note or ""))[:1000],
            "source": f"https://steamcommunity.com/sharedfiles/filedetails/?id={cid}",
            "mods": [{"workshop_id": w, "name": names.get(w, w)} for w in ids]}
