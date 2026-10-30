"""Local HTTP server: JSON API + static UI for every supported game. Binds to 127.0.0.1 only.

URLs:  /api/games, /api/settings, /api/update-check          app-wide
       /api/<game>/state, /api/<game>/playsets/..., ...      one game (ck3 / eu5 / vic3)
"""
import contextlib
import json
import os
import shutil
import tempfile
import threading
import time
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from . import APP_NAME, BUILD, __version__, collections, compare, detect, games as gamesmod, install, launch, order, presets, saves, scan, update, updates
from . import customgames, errorlog, gamelog, launcherdb, perflog, selfupdate, workshop
from .library import Library
from .paths import LOGO_TYPES, config_dir, fetch_best_logo, find_first, find_logo, game_version, launcher_exe, user_dirs, workshop_dirs
from .store import GlobalSettings, Store, write_load_file

STATIC = Path(__file__).parent / "static"
STATIC_TYPES = {"index.html": "text/html; charset=utf-8", "app.js": "text/javascript; charset=utf-8",
                "style.css": "text/css; charset=utf-8"}
MAX_JSON = 1024 * 1024
MAX_UPLOAD = 1024**3
CSP = ("default-src 'none'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; "
       "connect-src 'self'; base-uri 'none'; form-action 'none'; frame-ancestors 'none'")


MAX_TREE, MAX_RESULT = 5000, 30000
RESULT_CACHE = 64   # conflict answers kept per game (one per load order recently looked at)


class TooLarge(ValueError):
    pass


class GameApp:
    """Everything for one game. Paths resolve as: command-line flag > saved setting > auto-detection."""

    def __init__(self, game, user_dir=None, workshop_dir=None, game_dir=None, game_version_=None, game_exe=None,
                 store=None, library=None, logo=None, detect_libraries=(), opener=None, autodetect=True,
                 fetch_logos=False, auto_import_launcher=False):
        self.game = game
        self.auto_import_launcher = auto_import_launcher
        self.cfg = config_dir(game)
        self.store = store or Store(game=game)
        self.store.prune_empty_defaults()
        self.store.no_mods_provider = lambda: self.starting_mods([])
        self.library = library or Library(game=game)
        self.cli = {"user_dir": user_dir, "workshop_dir": workshop_dir, "game_dir": game_dir,
                    "game_version": game_version_}
        self.game_exe = game_exe
        self.logo_arg = logo
        self.fetch_logos = fetch_logos
        self.logo_pending = False
        self.extra_libraries = tuple(detect_libraries)
        self.opener = opener  # tests inject a fake "open this URL" (Steam)
        self.downloads = workshop.Downloads(game)
        self.lock = threading.RLock()
        self.mods, self.files, self.diff = {}, {}, {}
        self.scan_gen = 0            # grows whenever the mods on disk changed: everything computed from them is then stale
        self._results = {}           # conflict results by (load order, base game, scan_gen): switching playsets is a lookup
        self._trusted = set()        # parsed files already checked for changes since the last disk read
        self._scan_token = None      # the newest scan the user asked for; an older one stops
        self._prewarm = None
        self.prewarm_lock = None     # set by a Hub that wants the background pre-scan (the lock guarding app state)
        s = self.store.data["settings"]
        self.first_boot = not s.get("game_dir") and not game_dir and not s.get("setup_done")
        if self.first_boot and autodetect:
            found = detect.detect_all(game, self.extra_libraries)
            if found:  # take the first install; the UI asks the user to confirm it
                self.store.update_settings(game_dir=found[0]["path"])
        with perflog.timed(f"{game.id}: start-up scan"):
            self.apply_settings()
        if not self.first_boot:
            self.auto_import()
        try:
            self._log_start()
        except Exception as e:   # the log is a help, never a reason for the game not to open
            errorlog.write_exception("gamelog", e, self.game.id)

    def _log_start(self):
        by = {}
        for m in self.mods.values():
            by[m["source"]] = by.get(m["source"], 0) + 1
        g = self.game
        gamelog.log(g.id, f"{g.name} opened in the app", [
            f"game folder: {self.game_root or 'not set'}  (version {self.game_version or 'unknown'})",
            f"user folder: {self.user_dir or 'not found'}",
            f"workshop folder: {self.workshop_dir or 'not found'}",
            "mods found: " + (", ".join(f"{n} {k}" for k, n in sorted(by.items())) or "none"),
            f"playsets in the app: {', '.join(repr(p['name']) for p in self.store.data['playsets'].values()) or 'none'}",
            f"Play starts the game through: {self._play_via()}",
            *(["the game's own files:"] + ["  " + l for l in gamelog.snapshot(g, self.user_dir)] if g.kind == "paradox" else [])])

    # ---- paths ----
    def apply_settings(self):
        s, g = self.store.settings(), self.game
        gd = self.cli["game_dir"] or s["game_dir"]
        self.game_root = detect.find_install_root(gd, g) if gd else None
        self.game_dir = self.game_root / g.vanilla_dir_name if self.game_root else None
        pick = lambda cli, key, auto: Path(cli) if cli else (Path(s[key]) if s[key] else auto)
        self.user_dir = pick(self.cli["user_dir"], "user_dir", find_first(user_dirs(g)))
        self.workshop_dir = pick(self.cli["workshop_dir"], "workshop_dir",
                                 (detect.workshop_dir_for(self.game_root, g) if self.game_root else None)
                                 or find_first(workshop_dirs(g, self.extra_libraries)))
        self.game_version = self.cli["game_version"] or game_version(self.game_root, self.game, self.user_dir)
        self.logo = find_logo(g, self.logo_arg, self.game_root, self.extra_libraries)
        if not self.logo and not self.logo_arg and self.fetch_logos and not self.logo_pending and self.game.app_id != "0":
            self.logo_pending = True
            threading.Thread(target=self._fetch_logo, daemon=True, name="logo").start()
        self.rescan()

    def _fetch_logo(self):
        """No logo on this PC yet: get Steam's public art for the game once, in the background."""
        try:
            self.logo = fetch_best_logo(self.game)
        except Exception as e:  # offline or not on the CDN: the page keeps its neutral crest, nothing else breaks
            self.logo_error = f"{type(e).__name__}: {e}"
        finally:
            self.logo_pending = False

    def configure(self, b):
        """Save the setup dialog. The game folder may be any path inside the install."""
        if not isinstance(b, dict):
            raise ValueError("Invalid settings.")
        new = {}
        if b.get("game_dir"):
            root = detect.find_install_root(b["game_dir"], self.game)
            if not root:
                raise ValueError(f"That folder is not a {self.game.name} install "
                                 f"(expected a '{'/'.join(self.game.install_marker)}' folder inside it)")
            new["game_dir"] = str(root)
        for k in ("user_dir", "workshop_dir", "steamcmd"):
            if k in b:
                v = b[k]
                if not isinstance(v, str):
                    raise ValueError(f"'{k}' must be text.")
                v = v.strip()
                if v and not (Path(v).is_file() if k == "steamcmd" else Path(v).is_dir()):
                    raise ValueError(f"{'File' if k == 'steamcmd' else 'Folder'} does not exist: {v}")
                new[k] = v
        if "steam_user" in b:
            if not isinstance(b["steam_user"], str) or (b["steam_user"] and not workshop.USER_RE.match(b["steam_user"])):
                raise ValueError("The Steam account name may only contain letters, digits and _ . -")
            new["steam_user"] = b["steam_user"]
        if "include_vanilla" in b:
            if not isinstance(b["include_vanilla"], bool):
                raise ValueError("'include_vanilla' must be true or false.")
            new["include_vanilla"] = b["include_vanilla"]
        new["setup_done"] = True
        self.store.update_settings(**new)
        for k in ("game_dir", "user_dir", "workshop_dir"):
            if k in new:
                self.cli[k] = None
        self.apply_settings()
        self.auto_import()

    def starting_mods(self, mods):
        """What a new playset starts with: what was asked for, else the official modules a Bannerlord-style game needs."""
        if mods or not self.game.seed_mods:
            return mods
        have = {m["meta_id"]: mid for mid, m in self.mods.items() if m.get("meta_id")}
        return [have[i] for i in self.game.seed_mods if i in have and i != "Multiplayer"]

    # ---- the game's own launcher ----
    def launcher_info(self):
        """What the game's launcher has, for the Import menu."""
        what = "LauncherData.xml" if self.game.kind == "modules" else "launcher-v2.sqlite or playsets.json"
        try:
            src = self._launcher_source()
        except ValueError as e:
            return {"found": True, "db": "", "error": str(e), "playsets": [], "message": str(e)}
        if not src or not src[1]:
            return {"found": False, "db": "", "error": "", "playsets": [],
                    "message": f"No launcher playsets found for {self.game.name} (looked for {what} in {self.user_dir or 'its user folder'})."}
        files, sets = [src[0]], src[1]
        have = {ps.get("origin") for ps in self.store.data["playsets"].values()}
        seen = self.store.launcher_seen()
        return {"found": True, "db": str(files[0]), "error": "", "message": "",
                "playsets": [{"id": s["id"], "name": s["name"], "mods": len(s["mods"]), "active": s["active"],
                              "imported": f"launcher:{s['id']}" in have, "offered": f"launcher:{s['id']}" in seen} for s in sets]}

    def launcher_import(self, ids=None, only_unseen=False):
        """Create playsets from the launcher's. Without `ids` all of them are considered; one that is already here (it
        has the origin of that launcher playset) is skipped, so pressing the button again adds only what is new or what
        was deleted since. `only_unseen` (the automatic import) skips every playset that was ever imported before."""
        src = self._launcher_source()
        if not src:
            return {"imported": [], "skipped": 0, "lost": []}
        sets = src[1]
        have = {ps.get("origin") for ps in self.store.data["playsets"].values()}
        seen = self.store.launcher_seen()
        was_blank = all(not ps["mods"] for ps in self.store.data["playsets"].values())
        names = {ps["name"] for ps in self.store.data["playsets"].values()}
        done, skipped, lost, activate = [], 0, [], None
        for s in sets:
            origin = f"launcher:{s['id']}"
            if (ids is not None and s["id"] not in ids) or origin in have or (only_unseen and origin in seen):
                skipped += 1
                continue
            order_, off, gone = launcherdb.convert(s, self.mods)
            name = s["name"] if s["name"] not in names else f"{s['name']} (launcher)"
            pid = self.store.create(name, order_, off)
            self.store.set_origin(pid, origin)
            names.add(name)
            lost += [f"{s['name']}: {n}" for n in gone]
            done.append({"id": pid, "name": name, "mods": len(order_), "missing": sum(1 for m in order_ if m not in self.mods)})
            if s["active"]:
                activate = pid
        if done and was_blank and activate:
            self.store.data["active"] = activate
            self.store.save()
        return {"imported": done, "skipped": skipped, "lost": lost[:50]}

    def auto_import(self):
        """When the game opens: bring in launcher playsets that were never imported (never raises)."""
        if not self.auto_import_launcher:
            return
        try:
            with perflog.timed(f"{self.game.id}: import launcher playsets"):
                self.launcher_import(only_unseen=True)
        except Exception as e:
            errorlog.write_exception("launcher-import", e, self.game.id)

    def _launcher_source(self):
        """(where it was read, playsets) from the game's launcher, or None when it has none here."""
        if self.game.kind == "modules":
            f = Path(self.user_dir) / "Configs" / "LauncherData.xml" if self.user_dir else None
            return (f, launcherdb.read_bannerlord(self.user_dir)) if f and f.is_file() else None
        files = launcherdb.db_files(self.user_dir)
        if files:
            return files[0], launcherdb.read_playsets(files[0])
        sets = launcherdb.read_playsets_json(self.user_dir)  # EU5's launcher keeps its playsets in a plain JSON file
        return (Path(self.user_dir) / "playsets.json", sets) if sets else None

    def read_mods(self):
        """Read the mod folders. Slow on a big mod list, and touches no app state, so callers need not hold the lock."""
        with perflog.timed(f"{self.game.id}: read mod folders") as t:
            if self.game.kind == "modules":
                mods = scan.scan_modules(self.game_root, self.workshop_dir)
            else:
                mods = scan.scan_mods(self.user_dir, self.workshop_dir)
            t.note(mods=len(mods))
        return mods

    def apply_mods(self, mods, light=False):
        """Adopt a fresh mod list. Light (the window got focus): if nothing was added, changed or removed, everything
        worked out so far stays valid, so coming back to the window costs nothing. A full rescan (the button, a new
        path, an install) forgets the file listings too, so files edited inside a mod are seen."""
        changed = mods != self.mods
        self.mods = mods
        if changed or not light:
            self.files = {}
            self._results = {}
            self._trusted = set()
            self.scan_gen += 1
        with perflog.timed(f"{self.game.id}: update library file", quiet=True):
            self.diff = self.library.merge(self.mods)
        if changed or not light:
            self.start_prewarm()
        return changed

    def rescan(self, light=False):
        return self.apply_mods(self.read_mods(), light)

    # ---- conflicts: kept per load order, worked out ahead of the click ----
    def parse_cache_file(self):
        return config_dir() / "parse-cache.json.gz"

    def start_prewarm(self):
        """Work out the conflicts of every playset in the background (only when a Hub asked for it), so a click on a
        playset finds its answer ready. The first run after install is slow; its file parses are saved to disk, so
        later starts only look for changes."""
        if self.prewarm_lock is None or (self._prewarm and self._prewarm.is_alive()):
            return
        self._prewarm = threading.Thread(target=self._prewarm_run, daemon=True, name=f"prewarm-{self.game.id}")
        self._prewarm.start()

    def warm(self, say=None, lock=None):
        """Work out, now and in order, everything a click would otherwise wait for: the conflicts of every playset (the
        active one first). Used at start-up, before the window opens; `say(text)` reports how far it is."""
        say = say or (lambda _t: None)
        scan.load_cache(self.parse_cache_file())
        data = self.store.data
        ids = [p for p in [data["active"], *data["playsets"]] if p in data["playsets"]]
        ids = list(dict.fromkeys(ids))
        for n, pid in enumerate(ids, 1):
            name = data["playsets"][pid]["name"]
            head = f"playset {n} of {len(ids)} \"{name}\""
            say(head + " ...")
            with lock or contextlib.nullcontext():   # only the snapshot needs the app lock; the scan itself runs outside it
                job = self.conflicts_job(pid, progress=lambda text, head=head: say(f"{head}: {text}"))
            job()
        if scan.cache_dirty():
            with perflog.timed(f"{self.game.id}: save parse cache", quiet=True):
                scan.save_cache(self.parse_cache_file())

    def _prewarm_run(self):
        try:
            scan.load_cache(self.parse_cache_file())
            for _ in range(30):   # a round per interruption: the user's own request always goes first
                with self.prewarm_lock:
                    gen, data = self.scan_gen, self.store.data
                    ids = [data["active"]] + [p for p in data["playsets"] if p != data["active"]]
                    jobs = [self.conflicts_job(p, background=True) for p in ids if p in data["playsets"]]
                interrupted = False
                for job in jobs:
                    if self.scan_gen != gen:
                        break
                    if job().get("cancelled"):
                        interrupted = True
                        break
                else:
                    if self.scan_gen == gen:
                        break
                time.sleep(1.0 if interrupted else 0.1)
            if scan.cache_dirty():
                with perflog.timed(f"{self.game.id}: save parse cache", quiet=True):
                    scan.save_cache(self.parse_cache_file())
        except Exception as e:   # background help only: never take the app down
            errorlog.write_exception("prewarm", e, self.game.id)

    def diagnose(self):
        """The 'Check this game' report (beta): what the app found, step by step, and what it was looking for, so a game
        that does not work can be fixed by changing one folder or one field. -> {"checks": [{ok, label, detail}]}"""
        g, out = self.game, []
        add = lambda ok, label, detail: out.append({"ok": ok, "label": label, "detail": detail})
        marker = "/".join(g.install_marker)
        if self.game_root:
            add(True, "Game install", f"{self.game_root}  (found by its '{marker}' folder)")
        else:
            add(False, "Game install", f"Not found. The app looks for a folder that contains '{marker}' (Settings > Game). "
                                       f"It also searched the Steam libraries for '{g.install_dir_name}'.")
        if self.game_root:
            cd = Path(self.game_dir)
            add(cd.is_dir(), "Base game content", f"{cd}" + ("" if cd.is_dir() else "  (missing: check 'content folder' in the game definition)"))
        add(bool(self.game_version), "Game version", self.game_version or "Not read (optional). Only used for warnings.")
        ud = Path(self.user_dir) if self.user_dir else None
        add(bool(ud and ud.is_dir()), "User folder", f"{ud}" if ud and ud.is_dir() else
            f"Not found. Expected Documents/{(g.user_parent + '/') if g.user_parent else ''}{g.user_dir_name}. Set it in Settings > Storage.")
        if g.kind == "paradox" and ud and ud.is_dir():
            lf = ud / g.load_file
            add(True, f"Load file ({g.load_file})", f"{lf}" if lf.is_file() else "Not there yet. That is normal: it is written when you press Play, and the game reads it from here.")
            md = ud / "mod"
            add(md.is_dir(), "Local mods folder", f"{md}" if md.is_dir() else "No 'mod' folder in the user folder (no local mods yet).")
        ws = Path(self.workshop_dir) if self.workshop_dir else None
        if ws and ws.is_dir():
            try:
                n = sum(1 for _ in ws.iterdir())
            except OSError:
                n = 0
            add(True, "Steam Workshop folder", f"{ws}  ({n} item{'' if n == 1 else 's'})")
        else:
            add(False, "Steam Workshop folder", f"Not found (optional). Steam keeps Workshop mods in steamapps/workshop/content/{g.app_id}." if g.app_id != "0"
                else "Not found (optional). This game has no Steam app id.")
        by = {}
        for m in self.mods.values():
            by[m["source"]] = by.get(m["source"], 0) + 1
        add(bool(self.mods), "Mods found", ", ".join(f"{n} {k}" for k, n in sorted(by.items())) or
            "None. Mods are read from the local mod folders and the Workshop folder above.")
        src = None
        try:
            src = self._launcher_source()
        except Exception as e:  # a broken launcher file is a finding, not a crash
            add(False, "Launcher playsets", f"Could not be read: {type(e).__name__}: {e}")
        else:
            add(bool(src), "Launcher playsets", f"{src[0]}  ({len(src[1])} playset{'' if len(src[1]) == 1 else 's'})" if src
                else "Nothing to import (the game's own launcher file was not found; optional).")
        via = self._play_via()
        add(not via.startswith("nothing"), "Play starts the game through", via)
        return {"game": g.name, "checks": out, "beta": g.custom}

    # ---- views ----
    def state(self):
        d = self.store.data
        for pid in d["playsets"]:
            self.store.get(pid)
        s = self.store.settings()
        mods = [{**m, "change": self.library.change(m["id"])} for m in self.mods.values()]
        return {"game": self.game.public(), "mods": mods, "removed": self.library.removed(), "tag_counts": self.library.tag_counts(), "diff": self.diff, "scan_gen": self.scan_gen,
                "playsets": list(d["playsets"].values()), "no_mods": self.store.no_mods(), "fav_mods": list(self.store.data.get("fav_mods", [])), "active": d["active"],
                "user_dir": str(self.user_dir or ""), "workshop_dir": str(self.workshop_dir or ""),
                "game_root": str(self.game_root or ""), "game_version": self.game_version,
                "game_log": str(gamelog.log_path(self.game.id)), "has_logo": bool(self.logo), "logo_pending": self.logo_pending, "include_vanilla": s["include_vanilla"],
                "ui_scheme": s["ui_scheme"], "ui_text": s["ui_text"], "setup_done": s["setup_done"], "save_version_check": s["save_version_check"], "steamcmd": s["steamcmd"], "steam_user": s["steam_user"],
                "setup_needed": not s["setup_done"] and not (self.game_root and self.user_dir)}

    def analyse(self, pid, conflicts=True):
        """Problems with the load order (fast) and, unless conflicts=False, the file/definition conflicts (slow:
        reads every mod's files). The page asks for the fast part first and the conflicts afterwards."""
        ps = self.store.get(pid)
        enabled = [m for m in ps["mods"] if m not in ps["disabled"]]
        with perflog.timed(f"{self.game.id}: load-order check", quiet=True) as t:
            res = order.compute_order(self.mods, enabled, ps["auto_sort"], self.game_version)
            t.note(mods=len(enabled))
        out = {"issues": res["issues"], "notes": res["notes"], "conflicts": [], "counts": {}, "truncated": False,
               "pending": not conflicts}
        if conflicts:
            out.update(self.conflicts_job(pid, res["order"])())
        return out

    def conflicts_job(self, pid, ordr=None, background=False, progress=None):
        """Snapshot what the scan needs (quick, done under the app lock) and return the slow part as a function
        that can run without holding it, so switching games or editing a playset never waits for a scan.
        An answer worked out before is returned as it was. A request from the user stops any older scan (so clicks
        cannot pile up); the background pre-scan (`background=True`) is the one that gives way to the user."""
        if ordr is None:
            ps = self.store.get(pid)
            enabled = [m for m in ps["mods"] if m not in ps["disabled"]]
            ordr = order.compute_order(self.mods, enabled, ps["auto_sort"], self.game_version)["order"]
        mods, files, defs, gen, trusted = dict(self.mods), self.files, self.game.def_dirs, self.scan_gen, self._trusted
        van = None
        if self.game_dir and self.game_dir.is_dir() and self.store.settings()["include_vanilla"]:
            van = (self.game_dir, self.game.vanilla_only)
        key = (tuple(ordr), str(van[0]) if van else "", gen)
        hit = self._results.get(key)
        if hit is not None:
            return lambda: hit
        if progress:   # the start-up pass: nobody else is asking, so no giving way; report how far it is instead
            stop = lambda: False
        elif background:
            start = self._scan_token
            stop = lambda: time.sleep(0.002) or self._scan_token is not start   # also yields, so the page stays quick
        else:
            token = self._scan_token = object()
            stop = lambda: self._scan_token is not token

        def run():
            if not self.game.has_conflicts:  # Bannerlord modules do not share script folders: nothing meaningful to compare
                return {"conflicts": [], "counts": {}, "truncated": False, "pending": False}
            with perflog.timed(f"{self.game.id}: conflict scan", mods=len(ordr), base_game=bool(van)) as t:
                try:
                    conflicts = scan.find_conflicts(mods, ordr, files, defs, van, trusted=trusted, should_stop=stop, progress=progress)
                except scan.ScanCancelled:
                    t.note(cancelled=True)
                    return {"conflicts": [], "counts": {}, "truncated": False, "pending": True, "cancelled": True}
                t.note(found=len(conflicts))
            counts = {}
            for c in conflicts:
                k = "vanilla" if c.get("vanilla") else c["kind"]
                counts[k] = counts.get(k, 0) + 1
            cap = scan.MAX_PER_KIND * 4
            res = {"conflicts": conflicts[:cap], "counts": counts, "truncated": len(conflicts) > cap, "pending": False}
            if gen == self.scan_gen:   # the mods changed meanwhile: this answer is already out of date
                if len(self._results) >= RESULT_CACHE:
                    self._results.pop(next(iter(self._results)), None)
                self._results[key] = res
            return res
        return run

    def compare(self, a, b):
        res = compare.compare_playsets(self.mods, self.store.get(a), self.store.get(b))
        res["summary"] = {}
        for key, pid in (("a", a), ("b", b)):
            an = self.analyse(pid)
            res["summary"][key] = {"errors": sum(i["severity"] == "error" for i in an["issues"]),
                                   "warnings": sum(i["severity"] != "error" for i in an["issues"]),
                                   "conflicts": len([c for c in an["conflicts"] if c["kind"] != "patch"
                                                     and not c.get("vanilla")])}
        return res

    # ---- playsets ----
    def update(self, pid, fields):
        ps = self.store.update(pid, **fields)
        if ps["auto_sort"] and {"mods", "disabled", "auto_sort"} & set(fields):
            ps = self.store.update(pid, mods=order.sort_playset(self.mods, ps["mods"], ps["disabled"],
                                                                self.game_version))
        return ps

    def enable(self, pid, mid):
        ps = self.store.get(pid)
        if mid not in self.mods:
            raise ValueError("Unknown mod.")
        enabled = [m for m in ps["mods"] if m not in ps["disabled"]]
        wanted = order.missing_required(self.mods, [mid]) + [mid]
        mods = ps["mods"] + [m for m in wanted if m not in ps["mods"]]
        return self.update(pid, {"mods": mods, "disabled": [m for m in ps["disabled"] if m not in wanted]}) \
            if set(wanted) - set(enabled) else ps

    def bulk(self, pid, act):
        ps = self.store.get(pid)
        if act == "enable_all":
            return self.update(pid, {"disabled": []})
        if act == "disable_all":
            return self.store.update(pid, disabled=list(ps["mods"]))
        keep = [m for m in ps["mods"] if m in self.mods]  # prune: drop mods that are no longer installed
        return self.store.update(pid, mods=keep, disabled=[m for m in ps["disabled"] if m in keep])

    def import_playset(self, doc):
        pid, missing = self.store.import_shared(doc, self.mods, self.game.id)
        if self.store.get(pid)["auto_sort"]:
            self.update(pid, {"auto_sort": True})
        return {"id": pid, "missing": missing}

    # ---- presets / downloads ----
    def list_presets(self):
        return [presets.summarize(p, self.mods) for p in presets.load_all(self.game).values()]

    def apply_preset(self, preset_id):
        p = presets.load_all(self.game).get(preset_id)
        if not p:
            raise KeyError(preset_id)
        ids, off, missing = presets.to_playset_args(p, self.mods)
        pid = self.store.create(p["name"], ids, off, notes=(p["description"] or "")[:2000])
        self.update(pid, {"auto_sort": self.store.get(pid)["auto_sort"]})
        return {"id": pid, "missing": missing, "status": p["status"]}

    def save_preset(self, pid, preset_id, name):
        doc = presets.from_playset(self.game, self.store.get(pid), self.mods, preset_id, name)
        return presets.save_user_preset(self.game, doc)

    def import_collection(self, text, post=None):
        doc = collections.import_collection(self.game, text, post or collections.default_post)
        return presets.save_user_preset(self.game, doc)

    def mod_updates(self, post=None):
        return updates.check(self.mods, self.workshop_dir, self.game.app_id, post or collections.default_post)

    def _files_of(self, mid):
        m = self.mods.get(mid)
        if not m or not m["exists"]:
            return {}
        key = (m["root"], tuple(m.get("only", ())))
        if key not in self.files:
            self.files[key] = scan.list_files(m["root"], m.get("only", ()))
        return self.files[key]

    def _load_order(self, pid):
        ps = self.store.get(pid)
        enabled = [m for m in ps["mods"] if m not in ps["disabled"] and m in self.mods]
        return order.compute_order(self.mods, enabled, ps["auto_sort"], self.game_version)["order"]

    def tree_job(self, pid, mid=None):
        """Snapshot the load order now; the file listing (slow on first use) runs outside the lock."""
        ordr = self._load_order(pid)
        if mid is not None and mid not in self.mods:
            raise ValueError("Unknown mod.")
        mods = dict(self.mods)
        return (lambda: self.mod_tree(pid, mid, ordr, mods)) if mid is not None else (lambda: self.result_tree(pid, ordr, mods))

    def mod_tree(self, pid, mid, ordr=None, mods=None):
        """Files of one mod, each with the other enabled mods that also provide it (later in order wins)."""
        if mid not in self.mods:
            raise ValueError("Unknown mod.")
        ordr = ordr if ordr is not None else self._load_order(pid)
        pos = {m: i for i, m in enumerate(ordr)}
        mine = self._files_of(mid)
        others = {}
        for o in ordr:
            if o != mid:
                for rel in self._files_of(o):
                    if rel in mine:
                        others.setdefault(rel, []).append(o)
        out = []
        for rel in sorted(mine)[:MAX_TREE]:
            oth = others.get(rel, [])
            later = [o for o in oth if pos[o] > pos.get(mid, -1)]
            out.append({"path": rel, "overridden_by": later[-1] if later else None,
                        "overrides": [o for o in oth if o not in later]})
        return {"files": out, "total": len(mine), "truncated": len(mine) > MAX_TREE}

    def result_tree(self, pid, ordr=None, mods=None):
        """The merged file list of the whole playset: for each path, which mod supplies the winning copy."""
        ordr = ordr if ordr is not None else self._load_order(pid)
        win, count = {}, {}
        for i, m in enumerate(ordr):
            for rel in self._files_of(m):
                win[rel] = i
                count[rel] = count.get(rel, 0) + 1
        paths = sorted(win)[:MAX_RESULT]
        return {"mods": ordr, "files": [[r, win[r], count[r]] for r in paths],
                "total": len(win), "truncated": len(win) > MAX_RESULT}

    def download(self, ids, method):
        ids = workshop.clean_ids(ids)
        if method == "steam":
            return {"method": "steam", "opened": workshop.open_pages(ids, self.opener, delay=0.3)}
        if method == "steamcmd":
            s = self.store.settings()
            job = self.downloads.start(s["steamcmd"], s["steam_user"], ids)
            return {"method": "steamcmd", "job": job}
        raise ValueError("Unknown download method.")

    # ---- install / launch ----
    def install_zip(self, path, name):
        if self.game.kind == "modules":
            rep = install.install_modules_archive(path, self.game_root, name, self.cfg)
            self.rescan()
            return rep
        if not self.user_dir:
            raise ValueError(f"{self.game.name} user directory not found")
        rep = install.install_archive(path, self.user_dir, name, self.cfg)
        self.rescan()
        return rep

    def uninstall(self, mid):
        if self.game.kind == "modules":
            if mid not in self.mods or not self.game_root:
                raise ValueError("Unknown mod.")
            where = install.uninstall_module(self.game_root, self.mods[mid], self.cfg)
            self.rescan()
            return {"backup": where}
        if not self.user_dir or mid not in self.mods:
            raise ValueError("Unknown mod.")
        where = install.uninstall(self.user_dir, self.mods[mid], self.cfg)
        self.rescan()
        return {"backup": where}

    def saves_location(self, pid):
        """(folder the game will read saves from, key for the launch record)."""
        if self.store.get(pid)["separate_saves"]:
            d = self.cfg / "saves" / pid
            return d, f"playset:{pid}"
        return self.user_dir / saves.SAVES_DIR_NAME, "shared"

    def check_save_version(self, pid):
        """Raise SaveVersionWarning when the saves about to be used were made on another minor release."""
        if not self.store.settings()["save_version_check"] or not self.game_version or not self.user_dir:
            return
        folder, key = self.saves_location(pid)
        saved, source = saves.saved_on(self.cfg, key, folder)
        a, b = saves.minor_of(saved), saves.minor_of(self.game_version)
        if a and b and a != b:
            raise SaveVersionWarning(a, b, source)

    def _play_exe(self):
        """(executable, its fixed arguments) Play starts for a Paradox game: the one set with --game-exe, else the one
        the game's launcher starts (launcher-settings.json). Going through Steam would open the Paradox launcher, which
        writes its own playset over the load file. (None, []) = start through Steam (EU5 has no launcher folder)."""
        if self.game_exe:
            return self.game_exe, []
        exe, args = launcher_exe(self.game_root) if self.game.kind == "paradox" else (None, [])
        return (str(exe), args) if exe else (None, [])

    def _play_via(self):
        if self.game.kind == "modules" or self.game_exe:
            return "the game executable you set" if self.game_exe else "the game executable"
        exe, args = self._play_exe()
        if exe:
            return " ".join([exe, *args]) + " (directly, not through the Paradox launcher)"
        return "Steam (steam://run/%s)" % self.game.app_id if self.game.app_id != "0" else "nothing: set a game executable"

    def _chosen(self, pid, only):
        """Enabled mod ids (optionally a subset of them) and how many errors that subset has (None for no subset)."""
        ids = self.store.export(pid, self.mods)
        problems = None
        if only is not None:
            if not isinstance(only, list) or not all(isinstance(i, str) for i in only):
                raise ValueError("'only' must be a list of mod ids.")
            want = set(only)
            if not want <= set(ids):
                raise ValueError("Some chosen mods are not enabled in this playset.")
            if not want:
                raise ValueError("Choose at least one mod to launch with.")
            ids = [i for i in ids if i in want]
            problems = sum(1 for i in order.compute_order(self.mods, ids, False, self.game_version)["issues"]
                           if i["severity"] == "error")
        return ids, problems

    def _launch_modules(self, pid, ps, only):
        """Bannerlord-style start: no load file; the game is run with the module list on its command line."""
        if not self.game_root:
            raise ValueError(f"The {self.game.name} install folder is not set. Open Settings → Game.")
        exe = Path(self.game_exe) if self.game_exe else self.game_root.joinpath(*self.game.exe_rel)
        if not exe.is_file():
            raise ValueError(f"{self.game.name} was not found at {exe}. Set the game folder in Settings, or start it from Steam.")
        ids, problems = self._chosen(pid, only)
        modules = [self.mods[i]["meta_id"] for i in ids if i in self.mods and self.mods[i].get("meta_id")]
        if not modules:
            raise ValueError("Nothing to launch: no module in this playset can be found.")
        args = [*self.game.launch_prefix, module_list_argument(modules), *launch.validate_launch_args(ps["launch_args"])]
        gamelog.log(self.game.id, f"PLAY: playset {ps['name']!r}, {len(modules)} modules", [
            f"{i}. {mid}  {self.mods[mid]['name']!r}  {self.mods[mid]['root']}" for i, mid in enumerate(ids, 1) if mid in self.mods
        ] + [f"start: {exe} {' '.join(args)}"])
        res = launch.start(self.game, str(exe), args)
        gamelog.log(self.game.id, f"started the game: {res}")
        return {"written": len(modules), "file": "command line", "saves": None, "partial": only is not None,
                "problems": problems, "modules": modules, **res}

    def launch(self, pid, only=None, ack_version=False):
        """Start the game. `only` = a subset of this playset's enabled mods to launch with (the playset itself
        is not changed); the reply says how many problems that subset has so the UI can warn."""
        ps = self.store.get(pid)
        if self.game.kind == "modules":
            return self._launch_modules(pid, ps, only)
        if not self.user_dir:
            raise ValueError(f"{self.game.name} user directory not found")
        if not ack_version:
            self.check_save_version(pid)
        ids, problems = self._chosen(pid, only)
        gid = self.game.id
        gamelog.log(gid, f"PLAY: playset {ps['name']!r} ({pid}), {len(ids)} enabled mods" + (" (a chosen part of it)" if only is not None else ""), [
            f"{i}. {mid}  {self.mods[mid]['name']!r}  [{self.mods[mid]['source']}]  {self.mods[mid]['root']}" for i, mid in enumerate(ids, 1)])
        gamelog.log(gid, "before writing, the game's files say", gamelog.snapshot(self.game, self.user_dir))
        try:
            with perflog.timed(f"{gid}: write load file", mods=len(ids)):
                f = write_load_file(self.game, self.user_dir, self.mods, ids, ps["name"])
            gamelog.log(gid, f"wrote {f.name}" + (f" and {self.game.playsets_file} (playset {ps['name']!r} made the active one)" if self.game.playsets_file else ""),
                        gamelog.snapshot(self.game, self.user_dir))
            saves_note = None
            if ps["separate_saves"]:
                saves_note = saves.activate(self.user_dir / saves.SAVES_DIR_NAME, self.cfg / "saves" / pid)
            else:  # shared: all playsets use the game's normal folder, so undo a playset link left by an earlier launch
                saves_note = saves.deactivate(self.user_dir / saves.SAVES_DIR_NAME, self.cfg / "saves")
            exe, base_args = self._play_exe()
            res = launch.start(self.game, exe, [*base_args, *launch.validate_launch_args(ps["launch_args"])])
        except Exception as e:
            gamelog.log(gid, f"PLAY FAILED: {type(e).__name__}: {e}")
            raise
        gamelog.log(gid, f"started the game: {res}; saves: {saves_note or 'shared'}")
        gamelog.follow_up(self.game, self.user_dir)
        saves.record_launch(self.cfg, self.saves_location(pid)[1], self.game_version)
        return {"written": len(ids), "file": f.name, "saves": saves_note, "partial": only is not None,
                "problems": problems, **res}


def module_list_argument(module_ids):
    """The argument that tells a Bannerlord-style game which modules to load, in order."""
    return "_MODULES_*" + "*".join(module_ids) + "*_MODULES_"


class SaveVersionWarning(Exception):
    """Saves were made with a different game release than the one about to start. Needs the user's OK."""

    def __init__(self, saved, current, source):
        self.info = {"code": "save_version", "saved_on": saved, "game_version": current, "source": source}
        newer = tuple(map(int, saved.split("."))) > tuple(map(int, current.split(".")))
        self.message = (f"Your saves were made on game version {saved} but {('an older ' if newer else 'a newer ')}"
                        f"version ({current}) is about to start. Saves from {'newer' if newer else 'older'} versions can fail "
                        "to load or be damaged. Back them up, or launch anyway.")
        super().__init__(self.message)


class Hub:
    """All games plus app-wide state (settings, update check). Games are created on first use."""

    def __init__(self, overrides=None, settings=None, gamelist=None, factory=None, custom=None, prewarm=False):
        # Games the user added (beta) are only read for a normal start; a Hub built around given games has none unless asked
        self.custom = custom or (customgames.CustomGames.default() if gamelist is None else customgames.CustomGames())
        self.games = {g.id: g for g in (gamelist or gamesmod.GAMES.values())}
        self.games.update({g.id: g for g in self.custom.games()})
        self.overrides = overrides or {}  # {game id: GameApp kwargs from the command line}
        self.prewarm = prewarm            # work out every playset's conflicts in the background (the real app; not tests)
        self.settings = settings or GlobalSettings()
        self.apps = {}
        self.factory = factory or (lambda g, **kw: GameApp(g, **kw))
        self.lock = threading.RLock()  # one request at a time touches state; uploads/network stream outside it
        self._cache_lock = threading.Lock()
        self._update_cache = None
        self.update_pending = False
        self.client_errors = 0
        self.updater = selfupdate.Updater()
        self.ready = True      # False while the start-up pass runs (a copy that was just updated is not yet the one to switch to)
        self.last_ping = None  # when a page last said it is open (only used for a window this process cannot watch)
        self.updater_forced = False  # tests
        self.update_fetch = None  # tests inject a fake GitHub here

    def enable_prewarm(self):
        """From now on a game that changed is worked out again in the background (the start-up pass is over)."""
        self.prewarm = True
        for a in self.apps.values():
            a.prewarm_lock = self.lock

    @classmethod
    def single(cls, app, **kw):
        """A hub around one ready-made GameApp (tests, embedding)."""
        h = cls(gamelist=[app.game], **kw)
        h.apps[app.game.id] = app
        return h

    def app(self, game_id):
        if game_id not in self.games:
            raise KeyError(game_id)
        with self.lock:
            if game_id not in self.apps:
                self.apps[game_id] = self.factory(self.games[game_id], fetch_logos=self.settings.get()["fetch_logos"] and os.environ.get("MODMANAGER_FETCH_LOGOS") != "0",
                                                  auto_import_launcher=self.settings.get()["auto_import_launcher"] and os.environ.get("MODMANAGER_AUTO_IMPORT") != "0",
                                                  **self.overrides.get(game_id, {}))
                if self.prewarm:
                    self.apps[game_id].prewarm_lock = self.lock
                    self.apps[game_id].start_prewarm()
            return self.apps[game_id]

    def index(self):
        s = self.settings.get()
        return {"log_file": str(errorlog.log_path()), "can_self_update": selfupdate.can_self_update() or self.updater_forced, "games": [g.public() for g in self.games.values()], "last_game": s["last_game"],
                "custom_games": self.custom.defs, "game_templates": customgames.TEMPLATES,
                "version": __version__, "build": BUILD, "mode": os.environ.get("MODMANAGER_MODE", ""), "ready": self.ready, "settings": s, "update": self._update_cache[1] if self._update_cache else None,
                "update_pending": self.update_pending}

    def save_custom_game(self, b):
        """Add a game, or replace the one named by b['id'] (beta). -> the page's game list."""
        gid = b.get("id") or None
        if gid is not None and (not isinstance(gid, str) or gid not in self.custom.defs):
            raise ValueError("That game was not added by you, so it cannot be changed.")
        with self.lock:
            gid, game = self.custom.save(b.get("game"), gid, taken=self.games)
            self.games[gid] = game
            self.apps.pop(gid, None)   # rebuilt from the new definition on first use
        return {"id": gid, **self.index()}

    def remove_custom_game(self, gid, erase_data=False):
        """Forget an added game. Its playsets and settings stay in the app folder (and come back if a game with the same
        id is added again) unless erase_data is true. The game's own files are never touched."""
        if not isinstance(gid, str) or gid not in self.custom.defs:
            raise ValueError("That game was not added by you, so it cannot be removed.")
        with self.lock:
            self.custom.remove(gid)
            self.games.pop(gid, None)
            self.apps.pop(gid, None)
            if erase_data:
                shutil.rmtree(config_dir() / gid, ignore_errors=True)
        return self.index()

    def erase_all(self, confirm):
        """Experimental: delete everything this app saved (playsets, library, settings, backups, logos, presets of every
        game) so the next start is a fresh one. Only the app's own folders are removed; the games' folders, mods, saves
        and load files are never touched, and neither is the error log. -> {"erased": [names], "failed": [names]}"""
        if confirm != "ERASE":
            raise ValueError("Type ERASE to confirm.")
        base = config_dir()
        targets = [base / g for g in self.games] + [self.settings.path, base / "parse-cache.json.gz"]
        erased, failed = [], []
        with self.lock:
            self.apps.clear()  # GameApps are rebuilt (and rescan) on first use
            self.settings.data = {}
            for gid in list(self.custom.defs):
                self.games.pop(gid, None)
            self.custom.clear()
            for t in targets:
                try:
                    if t.is_symlink() or t.is_file():
                        t.unlink()
                    elif t.is_dir():
                        shutil.rmtree(t)
                    else:
                        continue
                    erased.append(t.name)
                except OSError as e:
                    failed.append(f"{t.name} ({e.strerror or e})")
        return {"erased": erased, "failed": failed}

    def check_update(self, force=False):
        """One GitHub request per 10 minutes at most. Network I/O happens outside the request lock."""
        import time
        with self._cache_lock:
            if not force and self._update_cache and time.time() - self._update_cache[0] < 600:
                return self._update_cache[1]
        with perflog.timed("check GitHub for a new version"):
            res = update.check_for_update(update.stable_current(), self.update_fetch)
            if BUILD:   # a test build follows the test builds: they carry the newest features, so they come before any release
                nightly = update.check_nightly(BUILD, self.update_fetch)
                if nightly["status"] in ("update", "current"):
                    res = nightly
        if res["status"] in ("update", "current", "no_releases"):
            with self._cache_lock:
                self._update_cache = (time.time(), res)
        return res

    def client_error(self, b):
        """The web page reports a script error or a failed request; it goes into the same log file."""
        if self.client_errors >= 200:  # a broken page must not be able to fill the disk
            return {"logged": False}
        self.client_errors += 1
        f = lambda k, n: str(b.get(k, ""))[:n] if isinstance(b, dict) else ""
        path = errorlog.write("page", f("message", 1000), f("stack", 8000), f"{f('game', 20)} {f('where', 200)}".strip())
        return {"logged": bool(path), "log_file": path}

    def check_on_launch(self):
        """If (and only if) the user turned the setting on, check in the background; returns the thread."""
        if not self.settings.get()["auto_update_check"]:
            return None
        self.update_pending = True

        def run():
            try:
                self.check_update()
            finally:
                self.update_pending = False
        t = threading.Thread(target=run, daemon=True)
        t.start()
        return t


def make_handler(hub):
    class H(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def _send(self, code, body, ctype="application/json", headers=()):
            self._status = code
            try:
                self._send_now(code, body, ctype, headers)
            except (ConnectionError, TimeoutError):  # the window or tab went away mid-answer: nothing to report
                self.close_connection = True

        def _send_now(self, code, body, ctype, headers):
            b = body if isinstance(body, bytes) else json.dumps(body).encode()
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(b)))
            self.send_header("Content-Security-Policy", CSP)
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("X-Frame-Options", "DENY")
            self.send_header("Referrer-Policy", "no-referrer")
            if not any(k.lower() == "cache-control" for k, _ in headers):
                self.send_header("Cache-Control", "no-store")
            for k, v in headers:
                self.send_header(k, v)
            self.end_headers()
            self.wfile.write(b)

        def _length(self, limit):
            try:
                n = int(self.headers.get("Content-Length") or 0)
            except ValueError:
                raise ValueError("Bad Content-Length.")
            if n < 0 or n > limit:
                raise TooLarge("Request too large.")
            return n

        def _body(self):
            b = json.loads(self.rfile.read(self._length(MAX_JSON)) or b"{}")
            if not isinstance(b, dict):
                raise ValueError("Expected a JSON object.")
            return b

        def _drain(self):
            """Read (and drop) a small request body before answering without using it. Closing a connection that still
            has unread data makes Windows reset it, and the client then sees an abort instead of the answer."""
            try:
                n = int(self.headers.get("Content-Length") or 0)
                if 0 < n <= MAX_JSON:
                    self.rfile.read(n)
            except (ValueError, OSError):
                pass

        def _host_ok(self):
            # guards against DNS rebinding: only answer for our own loopback host name
            return self.headers.get("Host", "").rsplit(":", 1)[0] in ("127.0.0.1", "localhost")

        def _route(self):
            """-> (parts, GameApp or None). Raises KeyError for an unknown game."""
            parts = self.path.split("?")[0].strip("/").split("/")
            if len(parts) >= 2 and parts[0] == "api" and parts[1] in hub.games:
                return ["api"] + parts[2:], hub.app(parts[1])
            return parts, None

        QUIET = ("/api/self-update", "/api/downloads")  # polled every second: log only when slow

        def _timed(self, method, run):
            path = self.path.split("?")[0]
            self._status = 0
            quiet = path.startswith(self.QUIET) or not path.startswith("/api/")
            if quiet and not path.startswith("/api/"):
                return run()  # the page itself and its files: not worth a line
            with perflog.timed(f"{method} {path}", quiet=quiet) as t:
                try:
                    return run()
                finally:
                    t.note(status=self._status)

        def do_GET(self):
            if hub.last_ping is not None:   # any request from a page shows it is open
                hub.last_ping = time.monotonic()
            self._timed("GET", self._do_get)

        def do_POST(self):
            self._timed("POST", self._do_post)

        def _do_get(self):
            p = self.path.split("?")[0].strip("/").split("/")
            if len(p) >= 4 and p[0] == "api" and p[2] in ("conflicts", "tree") and p[1] in hub.games:
                return self._heavy_get(p)
            if p == ["api", "ping"]:   # "this page is still open": no lock, no work
                if not self._host_ok():
                    return self._send(403, {"error": "bad host"})
                hub.last_ping = time.monotonic()
                return self._send(200, {})
            if len(p) == 3 and p[0] == "api" and p[1] in hub.games and p[2] == "logo":
                return self._logo(p[1])
            with hub.lock:
                self._get()

        def _logo(self, game_id):
            """The game's logo. Answered without creating the game (that reads every mod folder), from the PC's own files;
            only when none is there is the game created and, if it is fetching the logo from Steam, waited for. The browser
            keeps it (revalidated by ETag, so a new logo.png shows at once and an unchanged one costs nothing)."""
            if not self._host_ok():
                return self._send(403, {"error": "bad host"})
            try:
                app = hub.apps.get(game_id)
                logo = app.logo if app else None
                if not logo:
                    logo = find_logo(hub.games[game_id], hub.overrides.get(game_id, {}).get("logo"))
                if not logo:
                    app = hub.app(game_id)
                    deadline = time.time() + 8
                    while not app.logo and app.logo_pending and time.time() < deadline:
                        time.sleep(0.1)
                    logo = app.logo
                if not logo:
                    return self._send(404, {"error": "no logo"})
                st = logo.stat()
                tag = f'"{st.st_mtime_ns:x}-{st.st_size:x}"'
                head = [("ETag", tag), ("Cache-Control", "no-cache")]
                if self.headers.get("If-None-Match") == tag:
                    return self._send(304, b"", LOGO_TYPES[logo.suffix.lower()], head)
                return self._send(200, logo.read_bytes(), LOGO_TYPES[logo.suffix.lower()], head)
            except OSError:
                return self._send(404, {"error": "no logo"})
            except Exception as e:
                errorlog.write_exception("server", e, self.path.split("?")[0])
                return self._send(500, {"error": f"{type(e).__name__}: {e}", "log_file": str(errorlog.log_path())})

        def _heavy_get(self, p):
            """Slow read-only views: snapshot under the lock, compute outside it."""
            if not self._host_ok():
                return self._send(403, {"error": "bad host"})
            try:
                with hub.lock:
                    app = hub.app(p[1])
                    if p[2] == "conflicts":
                        job = app.conflicts_job(p[3])
                    elif len(p) == 4:
                        job = app.tree_job(p[3])
                    else:
                        job = app.tree_job(p[3], urllib.parse.unquote(p[4]))
                return self._send(200, job())
            except KeyError:
                return self._send(404, {"error": "no such playset"})
            except ValueError as e:
                return self._send(400, {"error": str(e)})
            except Exception as e:
                errorlog.write_exception("server", e, self.path.split("?")[0])
                return self._send(500, {"error": f"{type(e).__name__}: {e}", "log_file": str(errorlog.log_path())})

        def _do_post(self):
            parts = self.path.strip("/").split("/")
            if parts[-1] in ("install", "update-check", "downloads", "import-collection", "mod-updates", "self-update"):
                return self._post()  # slow network/disk work must not hold the lock
            if len(parts) == 3 and parts[0] == "api" and parts[1] in hub.games and parts[2] == "rescan":
                return self._rescan(parts[1])
            with hub.lock:
                self._post()

        def _get(self):
            if not self._host_ok():
                return self._send(403, {"error": "bad host"})
            try:
                parts, app = self._route()
                if parts == ["api", "games"]:
                    return self._send(200, hub.index())
                if parts == ["api", "self-update"]:
                    return self._send(200, hub.updater.status())
                if parts == ["api", "nightly"]:
                    return self._send(200, update.check_nightly(BUILD, hub.update_fetch))
                if app is not None:
                    if parts == ["api", "state"]:
                        return self._send(200, app.state())
                    if parts[:2] == ["api", "analyse"] and len(parts) == 3:
                        fast = "fast=1" in self.path.partition("?")[2].split("&")
                        return self._send(200, app.analyse(parts[2], conflicts=not fast))
                    if parts[:2] == ["api", "tree"] and len(parts) == 3:
                        return self._send(200, app.result_tree(parts[2]))
                    if parts[:2] == ["api", "tree"] and len(parts) == 4:
                        return self._send(200, app.mod_tree(parts[2], urllib.parse.unquote(parts[3])))
                    if parts[:2] == ["api", "compare"] and len(parts) == 4:
                        return self._send(200, app.compare(parts[2], parts[3]))
                    if parts[:2] == ["api", "playsets"] and len(parts) == 4 and parts[3] == "share":
                        doc = app.store.share(parts[2], app.mods, app.game.id)
                        return self._send(200, doc)
                    if parts == ["api", "launcher"]:
                        return self._send(200, app.launcher_info())
                    if parts == ["api", "diagnose"]:
                        return self._send(200, app.diagnose())
                    if parts == ["api", "presets"]:
                        return self._send(200, app.list_presets())
                    if parts == ["api", "downloads"]:
                        return self._send(200, app.downloads.status())
                    if parts == ["api", "detect"]:
                        return self._send(200, {"installs": detect.detect_all(app.game, app.extra_libraries)})
                    if parts == ["api", "inspect"]:
                        q = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query).get("path", [""])[0]
                        root = detect.find_install_root(q, app.game)
                        return self._send(200, {"install": detect.describe(root, app.game) if root else None})
                    if parts == ["api", "logo"]:
                        if not app.logo:
                            return self._send(404, {"error": "no logo"})
                        return self._send(200, app.logo.read_bytes(), LOGO_TYPES[app.logo.suffix.lower()])
            except KeyError:
                return self._send(404, {"error": "no such playset"})
            except ValueError as e:
                return self._send(400, {"error": str(e)})
            except Exception as e:  # never drop the connection: tell the page and keep a log entry
                where = self.path.split("?")[0]
                errorlog.write_exception("server", e, where)
                return self._send(500, {"error": f"{type(e).__name__}: {e}", "log_file": str(errorlog.log_path())})
            name = "index.html" if parts == [""] else parts[0] if len(parts) == 1 else None
            if name in STATIC_TYPES:  # fixed allow-list, never a path from the request
                return self._send(200, (STATIC / name).read_bytes(), STATIC_TYPES[name])
            self._send(404, {"error": "not found"})

        def _rescan(self, game_id):
            """Read the mod folders without holding the lock (seconds on a big list), then adopt the result under it.
            {"light": true} (window focus) keeps everything worked out so far when no mod changed."""
            host = self.headers.get("Host", "")
            origin = self.headers.get("Origin")
            if not self._host_ok() or (origin and origin.split("//", 1)[-1] != host):
                self._drain()
                return self._send(403, {"error": "bad origin"})
            try:
                light = self._body().get("light") is True
                with hub.lock:
                    app = hub.app(game_id)
                mods = app.read_mods()
                with hub.lock:
                    app.apply_mods(mods, light)
                    return self._send(200, app.state())
            except TooLarge as e:
                self.close_connection = True
                self._send(413, {"error": str(e)})
            except ValueError as e:
                self._send(400, {"error": str(e)})
            except Exception as e:
                errorlog.write_exception("server", e, f"POST {self.path.split('?')[0]}")
                self._send(500, {"error": f"{type(e).__name__}: {e}", "log_file": str(errorlog.log_path())})

        def _post(self):
            # reject cross-site requests: only same-origin requests from our own page
            host = self.headers.get("Host", "")
            origin = self.headers.get("Origin")
            if not self._host_ok() or (origin and origin.split("//", 1)[-1] != host):
                self._drain()
                return self._send(403, {"error": "bad origin"})
            try:
                parts, app = self._route()
                if app is None:  # app-wide routes
                    if parts == ["api", "self-update"]:
                        ch = self._body().get("channel", "stable")
                        if ch not in ("stable", "nightly", "release"):
                            raise ValueError("Unknown update channel.")
                        return self._send(200, hub.updater.start(channel=ch))
                    if parts == ["api", "client-error"]:
                        return self._send(200, hub.client_error(self._body()))
                    if parts == ["api", "update-check"]:
                        return self._send(200, hub.check_update(bool(self._body().get("force"))))
                    if parts == ["api", "settings"]:
                        return self._send(200, hub.settings.update(**self._body()))
                    if parts == ["api", "custom-games"]:
                        b = self._body()
                        return self._send(200, hub.save_custom_game(b))
                    if parts == ["api", "custom-games", "remove"]:
                        b = self._body()
                        return self._send(200, hub.remove_custom_game(b.get("id"), b.get("erase_data") is True))
                    if parts == ["api", "erase-all"]:
                        return self._send(200, hub.erase_all(self._body().get("confirm")))
                    return self._send(404, {"error": "not found"})
                if parts == ["api", "install"]:
                    return self._send(200, self._install(app))
                b = self._body()
                if parts == ["api", "paths"]:
                    app.configure(b)
                    return self._send(200, app.state())
                if parts == ["api", "fav-mod"]:
                    if not isinstance(b.get("on"), bool):
                        raise ValueError("'on' must be true or false.")
                    return self._send(200, {"fav_mods": app.store.set_favorite_mod(b.get("id", ""), b["on"])})
                if parts == ["api", "ui"]:
                    app.store.update_settings(**{k: b[k] for k in ("ui_scheme", "ui_text") if k in b})
                    return self._send(200, app.state())
                if parts == ["api", "skip-setup"]:
                    app.store.update_settings(setup_done=True)
                    app.auto_import()
                    return self._send(200, app.state())
                if parts == ["api", "rescan"]:
                    app.rescan()
                    return self._send(200, app.state())
                if parts == ["api", "playsets"]:
                    pid = app.store.create(b.get("name") or "New playset", app.starting_mods(b.get("mods")))
                    return self._send(200, {"id": pid})
                if parts == ["api", "import"]:
                    return self._send(200, app.import_playset(b))
                if parts == ["api", "launcher", "import"]:
                    ids = b.get("ids")
                    if ids is not None and not (isinstance(ids, list) and all(isinstance(x, str) for x in ids)):
                        raise ValueError("'ids' must be a list of launcher playset ids.")
                    return self._send(200, app.launcher_import(ids))
                if parts[:2] == ["api", "presets"] and len(parts) == 4 and parts[3] == "apply":
                    return self._send(200, app.apply_preset(parts[2]))
                if parts == ["api", "presets", "import-collection"]:
                    return self._send(200, app.import_collection(str(b.get("url", "")), getattr(self.server, "collection_post", None)))
                if parts == ["api", "mod-updates"]:
                    return self._send(200, app.mod_updates(getattr(self.server, "collection_post", None)))
                if parts == ["api", "downloads"]:
                    return self._send(200, app.download(b.get("ids"), str(b.get("method", "steam"))))
                if len(parts) == 4 and parts[:2] == ["api", "mods"] and parts[3] == "uninstall":
                    return self._send(200, app.uninstall(urllib.parse.unquote(parts[2])))
                if len(parts) == 4 and parts[:2] == ["api", "playsets"]:
                    pid, act = parts[2], parts[3]
                    if act == "update":
                        return self._send(200, app.update(pid, b))
                    if act == "merge":
                        return self._send(200, {"id": app.store.merge(pid, str(b.get("with", "")), str(b.get("name") or "Merged"))})
                    if act == "duplicate":
                        return self._send(200, {"id": app.store.duplicate(pid, b.get("name") or "Copy")})
                    if act == "delete":
                        app.store.delete(pid)
                        return self._send(200, {})
                    if act == "activate":
                        app.store.get(pid)
                        app.store.data["active"] = pid
                        app.store.save()
                        return self._send(200, {})
                    if act == "autosort":
                        ps = app.store.get(pid)
                        new = order.sort_playset(app.mods, ps["mods"], ps["disabled"], app.game_version)
                        return self._send(200, app.store.update(pid, mods=new))
                    if act == "enable":
                        return self._send(200, app.enable(pid, str(b.get("id"))))
                    if act in ("enable_all", "disable_all", "prune"):
                        return self._send(200, app.bulk(pid, act))
                    if act == "save-preset":
                        return self._send(200, app.save_preset(pid, str(b.get("id", "")), str(b.get("name", ""))))
                    if act == "launch":
                        res = app.launch(pid, b.get("only"), b.get("ack_version") is True)
                        hub.settings.update(last_game=app.game.id)
                        return self._send(200, res)
                self._send(404, {"error": "not found"})
            except KeyError:
                self._send(404, {"error": "no such playset"})
            except SaveVersionWarning as e:
                self._send(409, {"error": e.message, **e.info})
            except TooLarge as e:
                self.close_connection = True  # the unread body is never consumed
                self._send(413, {"error": str(e)})
            except (ValueError, install.UnsafeArchive) as e:
                self._send(400, {"error": str(e)})
            except Exception as e:  # surface to UI rather than hang the request
                errorlog.write_exception("server", e, f"POST {self.path.split('?')[0]}")
                self._send(500, {"error": f"{type(e).__name__}: {e}", "log_file": str(errorlog.log_path())})

        def _install(self, app):
            n = self._length(MAX_UPLOAD)
            name = os.path.basename(self.headers.get("X-Filename", "mod.zip"))
            stage = app.cfg / "staging"
            stage.mkdir(parents=True, exist_ok=True)
            fd, tmp = tempfile.mkstemp(dir=stage, suffix=".upload")
            try:
                with os.fdopen(fd, "wb") as f:  # stream to disk, never hold the upload in memory
                    left = n
                    while left > 0:
                        chunk = self.rfile.read(min(left, 1024 * 256))
                        if not chunk:
                            raise ValueError("Upload was cut off.")
                        f.write(chunk)
                        left -= len(chunk)
                with hub.lock:
                    return app.install_zip(tmp, name)
            finally:
                os.unlink(tmp)

    return H


def boot(hub, say=print, first=None):
    """Everything slow, done once before the window opens: read the mod folders of every game that has been used, load what
    was read last time, and work out the conflicts of every playset. A later start finds most of it saved, so this is
    quick; the first start with a big mod list is the long one. Progress goes to `say` (the terminal, when there is one)."""
    t0 = time.time()
    last = hub.settings.get().get("last_game")
    used = [g for g in hub.games if g == first or g == last or (config_dir() / g).is_dir()]
    if not used:
        return
    say("Getting ready. The first start with many mods takes a while; later starts are quick.")
    for gid in used:
        name = hub.games[gid].name
        t = time.time()
        say(f"{name}: reading mods ...")
        app = hub.app(gid)
        say(f"{name}: {len(app.mods)} mods ({time.time() - t:.1f} s)")
        if not app.mods:
            continue
        t = time.time()
        app.warm(lambda m, name=name: say(f"{name}: {m}"), hub.lock)
        say(f"{name}: ready ({time.time() - t:.1f} s)")
    say(f"Ready ({time.time() - t0:.1f} s).")


def adopts_open_window(mode, environ, app_window):
    """After an update by a version that does not close its own old window (no MODMANAGER_HANDOVER), in a browser's app
    window: that window reloads itself into the new copy, so the new copy must not open a second one."""
    return bool(mode == "window" and app_window and environ.get("MODMANAGER_RESTARTED") == "1" and not environ.get("MODMANAGER_HANDOVER"))


def watch_window(hub, quiet=150.0, grace=240.0):
    """For a window this process cannot watch (it belongs to a browser that was already running, which is what happens
    after an update): the app ends when no page has said it is open for `quiet` seconds. The page says so every few seconds
    and with every request; a laptop that slept is forgiven (the clocks stopped, the pages did not get to speak)."""
    started = tick = time.monotonic()
    while True:
        time.sleep(5)
        now = time.monotonic()
        if now - tick > 20:   # this loop was frozen: the computer was asleep
            started = now
            if hub.last_ping is not None:
                hub.last_ping = now
        tick = now
        seen = hub.last_ping
        if (seen is None and now - started > grace) or (seen is not None and now - seen > quiet):
            return


def serve(port=8765, open_browser=True, overrides=None, initial_game=None, window=False, **kw):
    """Run the app. `open_browser` shows the page; with `window` it gets its own window and closing it ends the app,
    otherwise it opens in the default browser and runs until Ctrl+C. The slow work (see boot) is done before the page opens."""
    import webbrowser
    from . import window as windowmod
    perflog.log(f"=== {APP_NAME} {__version__}{' test build ' + BUILD if BUILD else ''} starting (pid {os.getpid()}, "
                f"{'packaged' if selfupdate.frozen() else 'python edition' if selfupdate.pyz_path() else 'from source'}, port {port})")
    hub = Hub(overrides=overrides)
    hub.check_on_launch()  # no-op unless the user enabled "check for updates on launch"
    srv = None
    for attempt in range(40):  # a freshly updated copy waits for the old one to release the port
        try:
            srv = ThreadingHTTPServer(("127.0.0.1", port), make_handler(hub))
            break
        except OSError:
            if not os.environ.get("MODMANAGER_RESTARTED") or attempt == 39:
                raise
            time.sleep(0.5)
    perflog.log("server is listening")
    url = f"http://127.0.0.1:{port}/" + (f"#{initial_game}" if initial_game else "")
    mode = "window" if open_browser and window else "browser" if open_browser else "none"
    os.environ["MODMANAGER_MODE"] = mode  # an updated copy restarts the same way
    print(f"{APP_NAME} {__version__} running at {url}  (Ctrl+C to quit)", flush=True)
    print("  games: " + ", ".join(f"{g.id} ({g.name})" for g in hub.games.values()), flush=True)
    hub.ready = False
    threading.Thread(target=srv.serve_forever, daemon=True, name="server").start()

    def say(text):
        try:
            print(text, flush=True)
        except (OSError, ValueError):
            pass
        perflog.log("boot: " + text)

    try:
        if os.environ.get("MODMANAGER_BOOT") != "0":
            boot(hub, say, first=initial_game)
        if os.environ.get("MODMANAGER_PREWARM") != "0":
            hub.enable_prewarm()
        hub.ready = True
        if mode != "none":
            say("Opening the interface ...")
        # A copy that an OLD version (which does not know the new hand-over) just started inside a browser's app window: that
        # window reloads itself into this copy, so opening a second one would show two. Adopt it; its pings keep us alive.
        if adopts_open_window(mode, os.environ, windowmod.uses_app_window()):
            say("Continuing in the window that is already open.")
            watch_window(hub)
            srv.shutdown()
            srv.server_close()
            return
        if mode == "window":
            with perflog.timed("open the app window"):
                result = windowmod.show(url)
            if result == "closed":
                srv.shutdown()
                srv.server_close()
                return
            if result is None:
                webbrowser.open(url)  # no window backend here: the browser it is
            elif result == "detached":
                watch_window(hub)   # the window is a browser's, so closing it cannot end us: the pages' pings do
                srv.shutdown()
                srv.server_close()
                return
        elif mode == "browser":
            webbrowser.open(url)
        while True:  # keep serving until Ctrl+C (or, for the app window, until it is closed)
            time.sleep(3600)
    except KeyboardInterrupt:
        pass
