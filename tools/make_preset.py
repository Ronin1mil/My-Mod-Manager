"""Turn Steam Workshop collections into preset files in modmanager/presets/.

    python tools/make_preset.py vic3 2918558673 3373555715 https://steamcommunity.com/sharedfiles/filedetails/?id=3385177152
    python tools/make_preset.py auto <links>      # the game is read from each collection

One keyless request per collection to Steam's public API (the same code the app's "Import a Workshop collection" uses).
The preset ids are the collection's items, in the collection's order. Review the files, then commit them.
"""
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from modmanager import collections, games, presets  # noqa: E402


def clean(text):
    text = re.sub(r"\[/?[A-Za-z0-9*]+(?:=[^\]]*)?\]", " ", text)   # Steam BBCode tags
    text = re.sub(r"https?://\S+", "", text)
    return re.sub(r"\s+", " ", text).strip()


def make(game, cid, out):
    doc = collections.import_collection(game, cid)
    doc["name"] = re.sub(r"\s+", " ", re.sub(r"[^\w\s'.\-&()+,]", " ", doc["name"])).strip()  # no emoji or pipes in titles
    note = clean(doc["description"].split(". ", 1)[1] if ". " in doc["description"] else "")
    doc["id"] = f"{game.id}-" + re.sub(rf"^{game.id}-?", "", doc["id"])[:44].strip("-")
    doc["description"] = (f"From the Steam Workshop collection {cid}. " + (note[:380] + ("…" if len(note) > 380 else "") + " " if note else "")
                          + "Ids come from the collection (public, " + game.name + "); not tested in a game.")
    presets.validate(doc, game.id)
    path = out / f"{doc['id']}.json"
    path.write_text(json.dumps(doc, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return path, doc


def game_of(cid):
    """The game a collection is for, from Steam."""
    r = collections.default_post("/ISteamRemoteStorage/GetPublishedFileDetails/v1/", {"itemcount": 1, "publishedfileids[0]": cid})
    app = str(r["response"]["publishedfiledetails"][0].get("consumer_app_id", ""))
    for g in games.GAMES.values():
        if str(g.app_id) == app:
            return g
    raise ValueError(f"that collection is for Steam app {app or '?'}, which this app does not support")


if __name__ == "__main__":
    if len(sys.argv) < 3 or (sys.argv[1] not in games.GAMES and sys.argv[1] != "auto"):
        sys.exit(__doc__)
    out = Path(__file__).resolve().parent.parent / "modmanager" / "presets"
    for arg in sys.argv[2:]:
        try:
            g = games.GAMES[sys.argv[1]] if sys.argv[1] != "auto" else game_of(collections.parse_collection_id(arg))
            p, d = make(g, arg, out)
            print(f"{p.name}: {d['name']} ({len(d['mods'])} mods)")
        except ValueError as e:
            print(f"{arg}: {e}")
