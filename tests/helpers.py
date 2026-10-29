"""Shared builders: fake mods, fake game installs, and a running server for any game."""
import http.client
import json
import os
import tempfile
import threading
import unittest
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest import mock

from modmanager import games
from modmanager.library import Library
from modmanager.server import GameApp, Hub, make_handler
from modmanager.store import GlobalSettings, Store

ALL = list(games.GAMES.values())
APP_WIDE = ("/api/client-error", "/api/settings", "/api/update-check", "/api/games")


def mkmod(user, folder, name=None, deps=(), files=None, incompatible=(), meta_id="", layout=".metadata",
          rel_key="rel_type", extra=None, stub=True):
    """A local mod: <user>/mod/<folder>/ + <folder>.mod stub. `layout` is where metadata.json lives."""
    d = Path(user) / "mod" / folder
    (d / layout).mkdir(parents=True, exist_ok=True)
    rels = [{rel_key: "dependency", "display_name": x} if isinstance(x, str) else {rel_key: "dependency", **x} for x in deps]
    rels += [{rel_key: "incompatible", "display_name": x} for x in incompatible]
    meta = {"name": name or folder, "version": "1", "relationships": rels, **(extra or {})}
    if meta_id:
        meta["id"] = meta_id
    (d / layout / "metadata.json").write_text(json.dumps(meta))
    for rel, txt in (files or {}).items():
        (d / rel).parent.mkdir(parents=True, exist_ok=True)
        (d / rel).write_text(txt)
    if stub:
        (Path(user) / "mod" / f"{folder}.mod").write_text(f'name="{name or folder}"\npath="mod/{folder}"\n')
    return d


def mkworkshop(ws, wid, name, files=None, deps=()):
    d = Path(ws) / str(wid)
    (d / ".metadata").mkdir(parents=True, exist_ok=True)
    (d / ".metadata/metadata.json").write_text(json.dumps({
        "name": name, "version": "1", "relationships": [{"rel_type": "dependency", "display_name": x} for x in deps]}))
    for rel, txt in (files or {}).items():
        (d / rel).parent.mkdir(parents=True, exist_ok=True)
        (d / rel).write_text(txt)
    return d


def mkinstall(lib, game, version="1.2.3", files=None):
    """A fake Steam library containing the game. Returns the install root."""
    root = Path(lib) / "steamapps/common" / game.install_dir_name
    (root / Path(*game.install_marker)).mkdir(parents=True, exist_ok=True)
    (root / "launcher").mkdir(exist_ok=True)
    (root / "launcher/launcher-settings.json").write_text(json.dumps({"rawVersion": f"v{version}", "version": "x"}))
    (Path(lib) / "steamapps/workshop/content" / game.app_id).mkdir(parents=True, exist_ok=True)
    for rel, txt in (files or {}).items():
        p = root / "game" / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(txt)
    return root


class GameCase(unittest.TestCase):
    """Base for tests that need a running server. Subclass and set GAME, or build several with `serve`."""
    GAME = games.VIC3

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.r = Path(self.tmp.name)
        p = mock.patch.dict(os.environ, {"MODMANAGER_CONFIG_DIR": str(self.r / "cfg")})
        p.start()
        self.addCleanup(p.stop)
        self.addCleanup(self.tmp.cleanup)
        self.opened = []
        self.hub = Hub(settings=GlobalSettings(self.r / "g.json"),
                       factory=lambda g, **kw: GameApp(g, autodetect=False, opener=self.opened.append, **self.kw(g)))
        self.srv = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(self.hub))
        self.port = self.srv.server_address[1]
        threading.Thread(target=lambda: self.srv.serve_forever(poll_interval=0.01), daemon=True).start()
        self.addCleanup(self.srv.server_close)
        self.addCleanup(self.srv.shutdown)

    def kw(self, g):
        """Folders for each game under <tmp>/<game id>/. Override to add mods."""
        base = self.r / g.id
        (base / "user/mod").mkdir(parents=True, exist_ok=True)
        (base / "ws").mkdir(exist_ok=True)
        return {"user_dir": base / "user", "workshop_dir": base / "ws", "game_version_": "1.0.0",
                "store": Store(base / "playsets.json"), "library": Library(base / "library.json")}

    def user(self, g=None):
        return self.r / (g or self.GAME).id / "user"

    def ws(self, g=None):
        return self.r / (g or self.GAME).id / "ws"

    def req(self, method, path, body=None, headers=None, raw=None, game=None):
        g = game or self.GAME
        if path.startswith("/api/") and not path.startswith(APP_WIDE) and not any(
                path.startswith(f"/api/{x}/") for x in games.GAMES):
            path = f"/api/{g.id}/" + path[5:]
        c = http.client.HTTPConnection("127.0.0.1", self.port, timeout=10)
        h = dict(headers or {})
        data = raw
        if body is not None:
            data = json.dumps(body).encode()
            h.setdefault("Content-Type", "application/json")
        c.request(method, path, data, h)
        r = c.getresponse()
        txt = r.read()
        c.close()
        try:
            return r.status, json.loads(txt), r
        except ValueError:
            return r.status, txt, r

    def post(self, path, body=None, **kw):
        return self.req("POST", path, {} if body is None else body, **kw)

    def new_playset(self, mods=None, game=None):
        return self.post("/api/playsets", {"name": "T", "mods": mods or []}, game=game)[1]["id"]
