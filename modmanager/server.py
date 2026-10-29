"""Local HTTP server: JSON API + static UI for every supported game. Binds to 127.0.0.1 only.

URLs:  /api/games, /api/settings, /api/update-check          app-wide
       /api/<game>/state, /api/<game>/playsets/..., ...      one game (ck3 / eu5 / vic3)
"""
import json
import os
import shutil
import tempfile
import threading
import time
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from . import APP_NAME, __version__, collections, compare, detect, games as gamesmod, install, launch, order, presets, saves, scan, update, updates
from . import errorlog, launcherdb, selfupdate, workshop
from .library import Library
from .paths import LOGO_TYPES, config_dir, fetch_best_logo, find_first, find_logo, game_version, user_dirs, workshop_dirs
from .store import GlobalSettings, Store, write_load_file

STATIC = Path(__file__).parent / "static"
STATIC_TYPES = {"index.html": "text/html; charset=utf-8", "app.js": "text/javascript; charset=utf-8",
                "style.css": "text/css; charset=utf-8"}
MAX_JSON = 1024 * 1024
MAX_UPLOAD = 1024**3
CSP = ("default-src 'none'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; "
       "connect-src 'self'; base-uri 'none'; form-action 'none'; frame-ancestors 'none'")


MAX_TREE, MAX_RESULT = 5000, 30000


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
        s = self.store.data["settings"]
        self.first_boot = not s.get("game_dir") and not game_dir and not s.get("setup_done")
        if self.first_boot and autodetect:
            found = detect.detect_all(game, self.extra_libraries)
            if found:  # take the first install; the UI asks the user to confirm it
                self.store.update_settings(game_dir=found[0]["path"])
        self.apply_settings()
        if not self.first_boot:
            self.auto_import()

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
        self.game_version = self.cli["game_version"] or game_version(self.game_root, self.game)
        self.logo = find_logo(g, self.logo_arg, self.game_root, self.extra_libraries)
        if not self.logo and not self.logo_arg and self.fetch_logos and not self.logo_pending:
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

    def rescan(self):
        if self.game.kind == "modules":
            self.mods = scan.scan_modules(self.game_root, self.workshop_dir)
        else:
            self.mods = scan.scan_mods(self.user_dir, self.workshop_dir)
        self.files = {}  # file listings are cached per mod root until the next rescan
        self.diff = self.library.merge(self.mods)

    # ---- views ----
    def state(self):
        d = self.store.data
        for pid in d["playsets"]:
            self.store.get(pid)
        s = self.store.settings()
        mods = [{**m, "change": self.library.change(m["id"])} for m in self.mods.values()]
        return {"game": self.game.public(), "mods": mods, "removed": self.library.removed(), "tag_counts": self.library.tag_counts(), "diff": self.diff,
                "playsets": list(d["playsets"].values()), "no_mods": self.store.no_mods(), "fav_mods": list(self.store.data.get("fav_mods", [])), "active": d["active"],
                "user_dir": str(self.user_dir or ""), "workshop_dir": str(self.workshop_dir or ""),
                "game_root": str(self.game_root or ""), "game_version": self.game_version,
                "has_logo": bool(self.logo), "logo_pending": self.logo_pending, "include_vanilla": s["include_vanilla"],
                "ui_scheme": s["ui_scheme"], "ui_text": s["ui_text"], "setup_done": s["setup_done"], "save_version_check": s["save_version_check"], "steamcmd": s["steamcmd"], "steam_user": s["steam_user"],
                "setup_needed": not s["setup_done"] and not (self.game_root and self.user_dir)}

    def analyse(self, pid, conflicts=True):
        """Problems with the load order (fast) and, unless conflicts=False, the file/definition conflicts (slow:
        reads every mod's files). The page asks for the fast part first and the conflicts afterwards."""
        ps = self.store.get(pid)
        enabled = [m for m in ps["mods"] if m not in ps["disabled"]]
        res = order.compute_order(self.mods, enabled, ps["auto_sort"], self.game_version)
        out = {"issues": res["issues"], "notes": res["notes"], "conflicts": [], "counts": {}, "truncated": False,
               "pending": not conflicts}
        if conflicts:
            out.update(self.conflicts_job(pid, res["order"])())
        return out

    def conflicts_job(self, pid, ordr=None):
        """Snapshot what the scan needs (quick, done under the app lock) and return the slow part as a function
        that can run without holding it, so switching games or editing a playset never waits for a scan."""
        if ordr is None:
            ps = self.store.get(pid)
            enabled = [m for m in ps["mods"] if m not in ps["disabled"]]
            ordr = order.compute_order(self.mods, enabled, ps["auto_sort"], self.game_version)["order"]
        mods, files, defs = dict(self.mods), self.files, self.game.def_dirs
        van = None
        if self.game_dir and self.game_dir.is_dir() and self.store.settings()["include_vanilla"]:
            van = (self.game_dir, self.game.vanilla_only)

        def run():
            if not self.game.has_conflicts:  # Bannerlord modules do not share script folders: nothing meaningful to compare
                return {"conflicts": [], "counts": {}, "truncated": False, "pending": False}
            conflicts = scan.find_conflicts(mods, ordr, files, defs, van)
            counts = {}
            for c in conflicts:
                k = "vanilla" if c.get("vanilla") else c["kind"]
                counts[k] = counts.get(k, 0) + 1
            cap = scan.MAX_PER_KIND * 4
            return {"conflicts": conflicts[:cap], "counts": counts, "truncated": len(conflicts) > cap, "pending": False}
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
        res = launch.start(self.game, str(exe), args)
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
        f = write_load_file(self.game, self.user_dir, self.mods, ids)
        saves_note = None
        if ps["separate_saves"]:
            saves_note = saves.activate(self.user_dir / saves.SAVES_DIR_NAME, self.cfg / "saves" / pid)
        else:  # shared: all playsets use the game's normal folder, so undo a playset link left by an earlier launch
            saves_note = saves.deactivate(self.user_dir / saves.SAVES_DIR_NAME, self.cfg / "saves")
        res = launch.start(self.game, self.game_exe, launch.validate_launch_args(ps["launch_args"]))
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

    def __init__(self, overrides=None, settings=None, gamelist=None, factory=None):
        self.games = {g.id: g for g in (gamelist or gamesmod.GAMES.values())}
        self.overrides = overrides or {}  # {game id: GameApp kwargs from the command line}
        self.settings = settings or GlobalSettings()
        self.apps = {}
        self.factory = factory or (lambda g, **kw: GameApp(g, **kw))
        self.lock = threading.RLock()  # one request at a time touches state; uploads/network stream outside it
        self._cache_lock = threading.Lock()
        self._update_cache = None
        self.update_pending = False
        self.client_errors = 0
        self.updater = selfupdate.Updater()
        self.updater_forced = False  # tests
        self.update_fetch = None  # tests inject a fake GitHub here

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
            return self.apps[game_id]

    def index(self):
        s = self.settings.get()
        return {"log_file": str(errorlog.log_path()), "can_self_update": selfupdate.can_self_update() or self.updater_forced, "games": [g.public() for g in self.games.values()], "last_game": s["last_game"],
                "version": __version__, "settings": s, "update": self._update_cache[1] if self._update_cache else None,
                "update_pending": self.update_pending}

    def erase_all(self, confirm):
        """Experimental: delete everything this app saved (playsets, library, settings, backups, logos, presets of every
        game) so the next start is a fresh one. Only the app's own folders are removed; the games' folders, mods, saves
        and load files are never touched, and neither is the error log. -> {"erased": [names], "failed": [names]}"""
        if confirm != "ERASE":
            raise ValueError("Type ERASE to confirm.")
        base = config_dir()
        targets = [base / g for g in self.games] + [self.settings.path]
        erased, failed = [], []
        with self.lock:
            self.apps.clear()  # GameApps are rebuilt (and rescan) on first use
            self.settings.data = {}
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
        res = update.check_for_update(__version__, self.update_fetch)
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

        def _host_ok(self):
            # guards against DNS rebinding: only answer for our own loopback host name
            return self.headers.get("Host", "").rsplit(":", 1)[0] in ("127.0.0.1", "localhost")

        def _route(self):
            """-> (parts, GameApp or None). Raises KeyError for an unknown game."""
            parts = self.path.split("?")[0].strip("/").split("/")
            if len(parts) >= 2 and parts[0] == "api" and parts[1] in hub.games:
                return ["api"] + parts[2:], hub.app(parts[1])
            return parts, None

        def do_GET(self):
            p = self.path.split("?")[0].strip("/").split("/")
            if len(p) >= 4 and p[0] == "api" and p[2] in ("conflicts", "tree") and p[1] in hub.games:
                return self._heavy_get(p)
            with hub.lock:
                self._get()

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

        def do_POST(self):
            parts = self.path.strip("/").split("/")
            if parts[-1] in ("install", "update-check", "downloads", "import-collection", "mod-updates", "self-update"):
                return self._post()  # slow network/disk work must not hold the lock
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

        def _post(self):
            # reject cross-site requests: only same-origin requests from our own page
            host = self.headers.get("Host", "")
            origin = self.headers.get("Origin")
            if not self._host_ok() or (origin and origin.split("//", 1)[-1] != host):
                return self._send(403, {"error": "bad origin"})
            try:
                parts, app = self._route()
                if app is None:  # app-wide routes
                    if parts == ["api", "self-update"]:
                        return self._send(200, hub.updater.start())
                    if parts == ["api", "client-error"]:
                        return self._send(200, hub.client_error(self._body()))
                    if parts == ["api", "update-check"]:
                        return self._send(200, hub.check_update(bool(self._body().get("force"))))
                    if parts == ["api", "settings"]:
                        return self._send(200, hub.settings.update(**self._body()))
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


def serve(port=8765, open_browser=True, overrides=None, initial_game=None, window=False, **kw):
    """Run the app. `open_browser` shows the page; with `window` it gets its own window and closing it ends the app,
    otherwise it opens in the default browser and runs until Ctrl+C."""
    import webbrowser
    from . import window as windowmod
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
    url = f"http://127.0.0.1:{port}/" + (f"#{initial_game}" if initial_game else "")
    mode = "window" if open_browser and window else "browser" if open_browser else "none"
    os.environ["MODMANAGER_MODE"] = mode  # an updated copy restarts the same way
    print(f"{APP_NAME} {__version__} running at {url}  (Ctrl+C to quit)")
    print("  games: " + ", ".join(f"{g.id} ({g.name})" for g in hub.games.values()))
    if mode == "window":
        threading.Thread(target=srv.serve_forever, daemon=True, name="server").start()
        result = windowmod.show(url)
        if result == "closed":
            srv.shutdown()
            srv.server_close()
            return
        if result is None:
            webbrowser.open(url)  # no window backend here: the browser it is
        try:
            while True:  # "detached" or browser: keep serving until Ctrl+C
                time.sleep(3600)
        except KeyboardInterrupt:
            return
    if mode == "browser":
        webbrowser.open(url)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
