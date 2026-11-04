"""Random New World (beta), for Europa Universalis V only.

Random New World (RNW, https://github.com/Sir-Starch/eu5-random-new-world, MPL-2.0, Steam Workshop item 3829217331) is a
separate program that builds a new map for EU5. Every world it makes is an ordinary mod, a folder `rnw_exp_world_<id>` in
the game's `mod` folder. This module does not contain or copy RNW. It finds the generator the user installed, starts it
(its window, or its command line `rnw.cmd`), lists the worlds the user has with their settings, and turns one on in a
playset. docs/24-random-new-world-plan.md has the plan and docs/25-random-new-world.md what was built.

Where a world's settings come from (the list says which):
  its own files   `.metadata/rnw-library/world.json` inside the mod (code, preset, seed, generator, game build, record)
  its world code  `RNW1-...` in the mod's description: preset, seed, generator version, every changed setting (decode_code)
  the library     `rnw.cmd worlds` (also worlds that are not installed: kept copies and code-only worlds)
  this app        a record written here whenever this app makes or adds a world (`rnw-worlds.json` in the game's data folder)

Nothing is verified on a real PC yet (docs/25): file and command names come from RNW's open-source code.
"""
import hashlib
import json
import os
import re
import shutil
import struct
import subprocess
import threading
import time
import zlib
from pathlib import Path

from . import gamelog, order
from .paths import workshop_dirs
from .rnw_fields import CHANGE_FIELDS, PRESET_IDS

WORKSHOP_ID = "3829217331"
WORLD_PREFIX = "rnw_exp_world_"
HUB_FOLDER = "rnw_exp_hub"
RECEIPT = ".metadata/rnw-library/world.json"
METADATA = ".metadata/metadata.json"
MIN_FREE_BYTES = 2 * 1024 ** 3        # a world is about 1.2 GB
SEED_MAX = (1 << 64) - 1
MAX_JSON = 6 * 1024 * 1024
MAX_LOG = 30                          # lines of the generator's output kept for the page
MAX_RECORDS = 500

PRESETS = [
    {"id": "continents", "title": "Continents", "about": "Several large continents. A good first choice."},
    {"id": "small_continents", "title": "Small continents", "about": "Many smaller continents."},
    {"id": "supercontinent", "title": "Supercontinent", "about": "One huge landmass."},
    {"id": "archipelago", "title": "Archipelago", "about": "Large island groups."},
    {"id": "islands", "title": "Islands", "about": "Scattered single islands."},
    {"id": "wall", "title": "The Wall", "about": "A continent behind a barrier."},
]
PRESET_TITLES = {p["id"]: p["title"] for p in PRESETS}
NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)
ARG_OK = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:\-]{0,299}$")
OPT_OK = re.compile(r"^--[a-z][a-z\-]{0,30}$")
BAD_PATH = re.compile(r'[%^&|<>"!\x00-\x1f]')   # characters cmd.exe treats specially, even in a quoted .cmd argument
CODE_IN_TEXT = re.compile(r"RNW1(?:-[A-Za-z0-9]+)+", re.I)
PROGRESS = re.compile(r"^\[\s*(\d+)%\]\s*(start|done)?\s*(.*)$")
SKIP_EXE = re.compile(r"unins|uninstall|crash|setup|updater", re.I)
_records_lock = threading.Lock()

ALPHABET = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"
FOLD = {"O": "0", "I": "1", "L": "1"}
HEAD = struct.Struct(">BBQBBBB")
SECTIONS = {"new_world": "World", "natives": "Natives", "resources": "Resource", "rolls": "Re-roll", "mask": "Land picture"}


class CodeError(ValueError):
    """Text that is not a world code this app can read."""


# ---- world codes (the format is described in RNW's docs; the field table is in rnw_fields.py) ----
def _base32(digits):
    number = 0
    for c in digits:
        number = (number << 5) | ALPHABET.index(c)
    bits = len(digits) * 5
    size = bits // 8
    return (number >> (bits - size * 8)).to_bytes(size, "big")


def norm_code(text):
    """The code as RNW writes it ("RNW1-" and groups of five); raises CodeError when it is not one."""
    cleaned = "".join(FOLD.get(c, c) for c in re.sub(r"[\s\-_]+", "", str(text)).upper())
    if not cleaned.startswith("RNW1"):
        raise CodeError("That is not a Random New World code. A code starts with RNW1-.")
    digits = cleaned[4:]
    if not digits or len(digits) > 4000 or any(c not in ALPHABET for c in digits):
        raise CodeError("The world code has characters that cannot be in one.")
    return "-".join(["RNW1"] + [digits[i:i + 5] for i in range(0, len(digits), 5)])


def decode_code(text):
    """-> {"code", "preset", "seed" (int), "generator" ("1.1.0"), "changes" ({section: {field: value}} or None)}."""
    code = norm_code(text)
    body = _base32(code[5:].replace("-", ""))
    if len(body) < HEAD.size + 3:
        raise CodeError("The world code is too short.")
    payload, check = body[:-3], body[-3:]
    if hashlib.sha256(payload).digest()[:3] != check:
        raise CodeError("The world code has a typo (its check did not match).")
    fmt, preset, seed, major, minor, patch, flags = HEAD.unpack_from(payload)
    if fmt not in (1, 2) or preset not in PRESET_IDS:
        raise CodeError("This world code is from a version of Random New World this app does not know.")
    rest = payload[HEAD.size:]
    changes = None
    try:
        if flags & 1 and fmt == 2:
            changes = _expand(rest)
        elif flags & 1:
            (length,) = struct.unpack_from(">H", rest)
            d = zlib.decompressobj()
            raw = d.decompress(rest[2:2 + length], 200_000)
            changes = json.loads(raw)
            if not isinstance(changes, dict):
                raise ValueError("not an object")
        elif rest:
            raise ValueError("extra bytes")
    except (ValueError, struct.error, zlib.error, IndexError):
        raise CodeError("The changed settings in the world code are damaged.") from None
    return {"code": code, "preset": PRESET_IDS[preset], "seed": seed, "generator": f"{major}.{minor}.{patch}", "changes": changes}


def _expand(rest):
    if not rest:
        raise ValueError("empty")
    count, at, doc = rest[0], 1, {}
    for _ in range(count):
        if at >= len(rest) or rest[at] >= len(CHANGE_FIELDS):
            raise ValueError("bad field")
        section, field = CHANGE_FIELDS[rest[at]].split(".", 1)
        at += 1
        value = shift = 0
        while True:
            if at >= len(rest) or shift > 63:
                raise ValueError("bad number")
            byte = rest[at]
            at += 1
            value |= (byte & 0x7F) << shift
            shift += 7
            if not byte & 0x80:
                break
        doc.setdefault(section, {})[field] = value
    if at != len(rest):
        raise ValueError("extra bytes")
    return doc


def describe_changes(changes):
    """The settings a code changes from its world type's defaults, in words: [{"field", "label", "value"}]."""
    rows = []
    for section, fields in sorted((changes or {}).items()):
        if not isinstance(fields, dict):
            continue
        for field, v in sorted(fields.items()):
            name = re.sub(r"_(permille|px)$", "", field).replace("_", " ")
            if field.endswith("_permille") and isinstance(v, (int, float)) and not isinstance(v, bool):
                shown = f"{v / 10:g} %"
            elif field.endswith("_px"):
                shown = f"{v} px"
            elif isinstance(v, bool):
                shown = "yes" if v else "no"
            else:
                shown = str(v)
            rows.append({"field": f"{section}.{field}", "label": f"{SECTIONS.get(section, section)}: {name}", "value": shown[:80]})
    return rows


def flatten(obj, prefix="", out=None, depth=0):
    """A world's own record as readable rows [{"key", "value"}]. The layout is RNW's and may change, so this takes any
    JSON: scalars and short lists are kept, long text, big lists and file manifests are left out."""
    out = [] if out is None else out
    if len(out) >= 80 or depth > 4:
        return out
    if isinstance(obj, dict):
        for k, v in obj.items():
            if re.search(r"hash|digest|manifest|inputs|atlas|files", str(k), re.I):
                continue
            flatten(v, f"{prefix}.{k}" if prefix else str(k), out, depth + 1)
    elif isinstance(obj, (list, tuple)):
        if len(obj) <= 6 and all(isinstance(x, (str, int, float, bool)) for x in obj):
            out.append({"key": prefix, "value": ", ".join(str(x) for x in obj)[:120]})
    elif obj is not None and prefix:
        s = "yes" if obj is True else "no" if obj is False else str(obj)
        if len(s) <= 120:
            out.append({"key": prefix, "value": s})
    return out


# ---- the generator on this PC ----
class Generator:
    """The installed Random New World: its folder, `rnw.cmd` (commands), its launcher (the window)."""

    def __init__(self, folder, cmd=None, launcher=None, prefix=None, how=""):
        self.folder, self.cmd, self.launcher, self.prefix, self.how = Path(folder), cmd, launcher, prefix, how

    @property
    def can_run(self):
        return bool(self.prefix or self.cmd or self.launcher)

    def argv(self, args):
        if self.prefix:
            base = list(self.prefix)
        elif self.cmd:
            base = [str(self.cmd)]
        elif self.launcher:
            base = [str(self.launcher), "--cli"]   # the window program also takes --cli (docs/generator-guide.md)
        else:
            raise ValueError("Random New World's command line (rnw.cmd) was not found in " + str(self.folder))
        return base + list(args)

    def public(self):
        return {"folder": str(self.folder), "cmd": str(self.cmd or ""), "launcher": str(self.launcher or ""), "how": self.how,
                "can_open": bool(self.launcher), "can_run": self.can_run}


def _walk(folder, depth=3, cap=4000):
    todo, seen = [(Path(folder), 0)], 0
    while todo:
        d, lvl = todo.pop(0)
        try:
            with os.scandir(d) as it:
                for e in it:
                    seen += 1
                    if seen > cap:
                        return
                    try:
                        if e.is_dir(follow_symlinks=False):
                            if lvl < depth:
                                todo.append((Path(e.path), lvl + 1))
                        elif e.is_file():
                            yield Path(e.path)
                    except OSError:
                        continue
        except OSError:
            continue


def inspect_folder(folder, how=""):
    """-> Generator or None: does this folder hold Random New World (rnw.cmd and/or its launcher)?"""
    folder = Path(folder)
    if folder.is_file():
        folder = folder.parent
    if not folder.is_dir():
        return None
    cmd = launcher = None
    for f in _walk(folder):
        n = f.name.lower()
        if n == "rnw.cmd" and (cmd is None or len(f.parts) < len(cmd.parts)):
            cmd = f
        elif n.endswith(".exe") and not SKIP_EXE.search(n) and re.search(r"random.?new.?world|^rnw", n) \
                and (launcher is None or len(f.parts) < len(launcher.parts)):
            launcher = f
    return Generator(folder, cmd, launcher, how=how) if (cmd or launcher) else None


def find_generator(chosen="", candidates=()):
    """The folder the user chose first, then the usual places: [(folder, how)]."""
    for folder, how in ([(chosen, "the folder you chose")] if chosen else []) + list(candidates):
        g = inspect_folder(folder, how) if folder else None
        if g:
            return g
    return None


def parse_json(text):
    """The JSON object a command printed, even when progress lines come before it."""
    text = (text or "").strip()
    for start in [0] + [m.start() for m in re.finditer(r"(?m)^[\[{]", text)]:
        try:
            return json.loads(text[start:])
        except ValueError:
            continue
    return None


def check_args(args):
    for a in args:
        if not isinstance(a, str) or not (ARG_OK.match(a) or OPT_OK.match(a)):
            raise ValueError(f"'{str(a)[:40]}' is not allowed as a Random New World command argument.")
    return list(args)


def run_cli(gen, args, timeout=60, runner=subprocess.run):
    """One quick command of the generator. Arguments are checked first (a .cmd file runs through cmd.exe), and the
    command is started from an argument list, never a shell string. -> (exit code, text, error text)"""
    argv = gen.argv(check_args(args))
    r = runner(argv, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=timeout,
               cwd=str(gen.folder), creationflags=NO_WINDOW)
    return r.returncode, r.stdout or "", r.stderr or ""


def _error_text(out, err):
    lines = [l.strip() for l in (err + "\n" + out).splitlines() if l.strip()]
    hit = [l for l in lines if l.lower().startswith("error")]
    return (hit[-1] if hit else lines[-1] if lines else "the generator printed nothing")[:300]


# ---- reading worlds ----
def _json_file(path):
    try:
        if path.is_symlink() or not path.is_file() or path.stat().st_size > MAX_JSON:
            return None
        v = json.loads(path.read_text(encoding="utf-8-sig", errors="replace"))
        return v if isinstance(v, dict) else None
    except (OSError, ValueError):
        return None


def read_world_folder(folder):
    """One installed world from its own files. -> dict (see `entry`) or None when it is not a Random New World mod."""
    folder = Path(folder)
    meta = _json_file(folder / METADATA) or {}
    receipt = _json_file(folder / RECEIPT)
    if not folder.name.startswith(WORLD_PREFIX) and receipt is None:
        return None
    e = entry(folder=folder.name, installed=True, path=str(folder))
    e["name"] = str(meta.get("name") or "")[:80]
    e["generator"] = str(meta.get("version") or "")
    code = None
    if receipt:
        e["specs_from"].append("the world's own files")
        code = receipt.get("code")
        for k in ("game_build", "created", "seconds", "parent", "part"):
            if receipt.get(k) not in (None, ""):
                e[k] = receipt[k]
        if receipt.get("name"):
            e["name"] = str(receipt["name"])[:80]
        if receipt.get("generator"):
            e["generator"] = str(receipt["generator"])
        e["details"] = flatten(receipt.get("record"))
        e["id"] = str(receipt.get("id") or "")
    m = CODE_IN_TEXT.search(str(meta.get("short_description", "")))
    code = code or (m.group(0) if m else None)
    if code:
        apply_code(e, code)
    if not e["id"]:
        e["id"] = folder.name[len(WORLD_PREFIX):] if folder.name.startswith(WORLD_PREFIX) else folder.name
    if not e["created"]:
        try:
            e["created"] = int((folder / METADATA).stat().st_mtime)
        except OSError:
            pass
    return e


def entry(**kw):
    e = {"folder": "", "path": "", "installed": False, "id": "", "mod_id": "", "name": "", "tag": "", "code": "", "valid_code": False,
         "preset": "", "preset_title": "", "seed": "", "generator": "", "game_build": "", "created": 0, "seconds": 0,
         "changes": [], "details": [], "place": "", "notes": "", "starred": False, "parent": "", "part": "",
         "made_here": False, "how": "", "specs_from": [], "in_playset": "none", "problem": ""}
    e.update(kw)
    return e


def apply_code(e, text):
    """Fill the settings of a world from its world code. A bad code is shown as a problem, not an error."""
    try:
        d = decode_code(text)
    except CodeError as err:
        e["problem"] = str(err)
        e["code"] = str(text)[:200]
        return False
    e.update(code=d["code"], valid_code=True, preset=d["preset"], preset_title=PRESET_TITLES.get(d["preset"], d["preset"]),
             seed=str(d["seed"]), changes=describe_changes(d["changes"]))
    e["generator"] = e["generator"] or d["generator"]
    if "the world's code" not in e["specs_from"]:
        e["specs_from"].append("the world's code")
    return True


class Records:
    """What this app knows about worlds it made or added itself (`rnw-worlds.json` in the game's data folder)."""

    def __init__(self, path):
        self.path = Path(path)

    def load(self):
        d = _json_file(self.path) or {}
        w = d.get("worlds")
        return w if isinstance(w, dict) else {}

    def put(self, code, rec):
        with _records_lock:
            worlds = self.load()
            worlds[code] = {**worlds.get(code, {}), **rec}
            for old in sorted(worlds, key=lambda k: worlds[k].get("requested_at", 0))[:-MAX_RECORDS]:
                del worlds[old]
            tmp = self.path.with_suffix(".tmp")
            tmp.write_text(json.dumps({"schema": 1, "worlds": worlds}, indent=1), encoding="utf-8")
            os.replace(tmp, self.path)


def merge_worlds(installed, library, records, mod_ids=None):
    """One list from the three sources. Same world = same world code, else same mod folder."""
    mod_ids = mod_ids or {}
    out, by_code, by_folder = [], {}, {}

    def add(e):
        out.append(e)
        if e["code"] and e["valid_code"]:
            by_code[e["code"]] = e
        if e["folder"]:
            by_folder[e["folder"]] = e
        return e

    for e in installed:
        add(e)
    for row in library:
        if not isinstance(row, dict):
            continue
        try:
            code = norm_code(row.get("code", ""))
        except CodeError:
            code = ""
        folder = WORLD_PREFIX + str(row.get("id", ""))
        e = by_code.get(code) if code else None
        e = e or by_folder.get(folder)
        if e is None:
            e = add(entry(folder=folder if row.get("place") == "in_game" else "", id=str(row.get("id", ""))))
            if code:
                apply_code(e, code)
                by_code[code] = e
        e["specs_from"].append("the generator's library")
        e["place"] = str(row.get("place") or e["place"])[:20]
        for k in ("game_build", "parent", "part", "notes"):
            if row.get(k) and not e[k]:
                e[k] = str(row[k])[:300]
        e["starred"] = bool(row.get("starred"))
        e["tag"] = str(row.get("tag") or e["tag"])[:8]
        e["name"] = str(row.get("name") or e["name"])[:80]
        if not e["preset"] and row.get("preset"):
            e["preset"], e["preset_title"] = str(row["preset"]), PRESET_TITLES.get(row["preset"], str(row["preset"]))
        if not e["seed"] and row.get("seed") is not None:
            e["seed"] = str(row["seed"])
        e["generator"] = e["generator"] or str(row.get("generator") or "")
        if row.get("created") and not e["created"]:
            e["created"] = int(row["created"]) if str(row["created"]).isdigit() else 0
    for code, rec in records.items():
        e = by_code.get(code)
        if e is None:
            if rec.get("state") != "done":
                continue
            e = add(entry(id=rec.get("id", ""), folder=""))
            apply_code(e, code)
            e["place"] = "code_only"
            by_code[code] = e
        e["made_here"] = True
        e["how"] = str(rec.get("how", ""))[:60]
        e["specs_from"].append("this app's record")
        for k, f in (("game_build", "game_version"), ("seconds", "seconds")):
            if rec.get(f) and not e[k]:
                e[k] = rec[f]
        if rec.get("requested_at") and not e["created"]:
            e["created"] = int(rec["requested_at"])
        if rec.get("summary") and not e["details"]:
            e["details"] = flatten(rec["summary"])
    for e in out:
        e["place"] = e["place"] or ("in_game" if e["installed"] else "code_only")
        e["tag"] = e["tag"] or (e["id"][:4].upper() if e["id"] else "")
        e["name"] = e["name"] or (f"{e['preset_title']} {e['tag']}".strip() or e["folder"])
        e["mod_id"] = mod_ids.get(e["folder"], "")
    out.sort(key=lambda e: (not e["installed"], -(e["created"] or 0), e["name"].lower()))
    return out


# ---- running the generator in the background ----
class Jobs:
    """One generator job at a time (a build takes minutes). The request that starts it returns at once."""

    def __init__(self, popen=subprocess.Popen):
        self.popen = popen
        self.lock = threading.Lock()
        self.job = None
        self.proc = None
        self._n = 0

    def busy(self):
        with self.lock:
            return bool(self.job and self.job["state"] == "running")

    def start(self, kind, label, argv, cwd, on_done=None):
        with self.lock:
            if self.job and self.job["state"] == "running":
                raise ValueError("Random New World is already working on something. Wait for it to finish, or cancel it.")
            self._n += 1
            job = self.job = {"id": self._n, "kind": kind, "label": label, "state": "running", "percent": 0, "stage": "Starting",
                              "log": [], "error": "", "result": None, "started": time.time(), "finished": 0, "cancel": False}
        threading.Thread(target=self._run, args=(job, argv, cwd, on_done), daemon=True, name="rnw-job").start()
        return self.public(job)

    def _run(self, job, argv, cwd, on_done):
        out, proc = [], None
        try:
            proc = self.proc = self.popen(argv, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding="utf-8",
                                          errors="replace", cwd=str(cwd), creationflags=NO_WINDOW)
            for raw in proc.stdout:
                line = raw.rstrip()
                if not line:
                    continue
                m = PROGRESS.match(line)
                if m:
                    job["percent"] = min(100, int(m.group(1)))
                    job["stage"] = (m.group(3) or job["stage"])[:120]
                else:
                    if len(out) < 4000:
                        out.append(line)
                job["log"] = (job["log"] + [line[:200]])[-MAX_LOG:]
            rc = proc.wait()
            text = "\n".join(out)
            if job["cancel"]:
                job["state"] = "cancelled"
            elif rc == 0:
                job["state"], job["percent"] = "done", 100
                job["result"] = parse_json(text)
            else:
                job["state"], job["error"] = "failed", _error_text(text, "")
        except Exception as e:   # the program could not start, or the pipe broke: say so on the page
            job["state"], job["error"] = "failed", f"{type(e).__name__}: {e}"[:300]
        finally:
            job["finished"] = time.time()
            try:
                if proc is not None and proc.stdout:
                    proc.stdout.close()
            except OSError:
                pass
            self.proc = None
            if on_done:
                try:
                    on_done(job)
                except Exception as e:
                    job["error"] = job["error"] or f"The world was made, but the app could not finish: {e}"[:300]

    def cancel(self):
        with self.lock:
            job, proc = self.job, self.proc
            if not job or job["state"] != "running":
                return self.status()
            job["cancel"] = True
        if proc is not None:
            _kill_tree(proc)
        return self.status()

    def public(self, job):
        if not job:
            return None
        end = job["finished"] or time.time()
        return {**{k: job[k] for k in ("id", "kind", "label", "state", "percent", "stage", "log", "error", "result")},
                "elapsed": round(end - job["started"])}

    def status(self):
        return self.public(self.job)


def _kill_tree(proc):
    try:
        if os.name == "nt":
            subprocess.run(["taskkill", "/PID", str(proc.pid), "/T", "/F"], capture_output=True, timeout=20, creationflags=NO_WINDOW)
        else:
            proc.kill()
    except Exception:
        try:
            proc.kill()
        except Exception:
            pass


# ---- the part that belongs to one game ----
class Manager:
    """Random New World for one GameApp (Europa Universalis V)."""

    def __init__(self, app, runner=subprocess.run, popen=subprocess.Popen, generator=None):
        self.app = app
        self.runner, self.popen = runner, popen
        self.jobs = Jobs(popen)
        self._generator = generator            # tests hand in a stub; None = look on this PC
        self.records = Records(app.cfg / "rnw-worlds.json")

    # -- finding it --
    def generator(self):
        if self._generator is not None:
            return self._generator
        app = self.app
        cands = []
        for ws in workshop_dirs(app.game, app.extra_libraries):
            cands.append((Path(ws) / WORKSHOP_ID, "the Steam Workshop"))
        if app.workshop_dir:
            cands.append((Path(app.workshop_dir) / WORKSHOP_ID, "the Steam Workshop"))
        if app.user_dir:
            cands.append((Path(app.user_dir) / "mod" / HUB_FOLDER, "your mod folder"))
        return find_generator(app.store.settings().get("rnw_dir", ""), cands)

    def set_folder(self, path):
        path = str(path or "").strip()
        if path and not inspect_folder(path):
            raise ValueError("Random New World was not found in that folder (no rnw.cmd and no Random New World program).")
        self.app.store.update_settings(rnw_dir=path)
        gen = self.generator()
        return gen.public() if gen else None

    # -- listing --
    def list_job(self):
        """Snapshot what the lock protects, return the function that reads the disk (run it without the lock)."""
        app = self.app
        gen, user_dir = self.generator(), app.user_dir
        ps = app.store.data["playsets"].get(app.store.data["active"]) if app.store.data.get("active") else None
        enabled = {m for m in (ps["mods"] if ps else []) if m not in ps["disabled"]}
        inlist = set(ps["mods"]) if ps else set()
        mod_ids = {Path(m["root"]).name: mid for mid, m in app.mods.items() if m.get("root") and m.get("source") != "vanilla"}
        hub = [mid for mid, m in app.mods.items() if is_hub(m)]
        version, pid = app.game_version, ps["id"] if ps else ""
        job = self.jobs.status()

        def run():
            notes, installed = [], []
            mod_dir = Path(user_dir) / "mod" if user_dir else None
            if mod_dir and mod_dir.is_dir():
                try:
                    names = sorted(os.listdir(mod_dir))
                except OSError:
                    names = []
                for n in names:
                    if (mod_dir / n).is_dir():
                        e = read_world_folder(mod_dir / n)
                        if e:
                            installed.append(e)
            library, cli = [], {"ok": False, "error": ""}
            if gen and gen.can_run:
                try:
                    rc, out, err = run_cli(gen, ["worlds"], timeout=45, runner=self.runner)
                    data = parse_json(out) if rc == 0 else None
                    if isinstance(data, list):
                        library, cli["ok"] = data, True
                    else:
                        cli["error"] = _error_text(out, err) if rc else "The generator's list of worlds could not be read."
                except (OSError, subprocess.SubprocessError) as e:
                    cli["error"] = f"{type(e).__name__}: {e}"[:300]
            worlds = merge_worlds(installed, library, self.records.load(), mod_ids)
            for w in worlds:
                mid = w["mod_id"]
                w["in_playset"] = "none" if not mid or mid not in inlist else "on" if mid in enabled else "off"
            if gen is None:
                notes.append("Random New World was not found on this PC. Subscribe to it on the Steam Workshop (item "
                             f"{WORKSHOP_ID}), or download it from GitHub, then press Find again or choose its folder.")
            elif not gen.can_run:
                notes.append("Random New World's folder was found, but not its command line (rnw.cmd).")
            elif not cli["ok"]:
                notes.append("The generator's own list of worlds could not be read, so only worlds installed in your mod folder "
                             "are shown. " + cli["error"])
            return {"generator": gen.public() if gen else None, "worlds": worlds, "cli": cli, "notes": notes, "presets": PRESETS,
                    "hub": {"installed": bool(hub), "enabled": any(h in enabled for h in hub)}, "playset": pid,
                    "game_version": version, "job": job, "free_gb": _free_gb(user_dir), "user_dir": str(user_dir or "")}
        return run

    # -- starting things --
    def open_generator(self):
        gen = self.generator()
        if gen is None or not gen.launcher:
            raise ValueError("Random New World's program was not found. Choose its folder first.")
        self.popen([str(gen.launcher)], cwd=str(gen.launcher.parent), close_fds=True, stdin=subprocess.DEVNULL,
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        gamelog.log(self.app.game.id, f"Random New World opened: {gen.launcher}")
        return {"opened": str(gen.launcher)}

    def _need_cli(self):
        gen = self.generator()
        if gen is None or not gen.can_run:
            raise ValueError("Random New World's command line (rnw.cmd) was not found. Choose its folder first.")
        return gen

    def _need_space(self):
        free = _free_gb(self.app.user_dir)
        if free is not None and free < MIN_FREE_BYTES / 1024 ** 3:
            raise ValueError(f"Only {free:.1f} GB are free where your mods are. A world needs about 1.2 GB; free some space first.")

    def new_world(self, preset=None, seed=None, code=None):
        """Make a world: from a world code, or from a world type and a seed (empty = random). Runs in the background."""
        gen = self._need_cli()
        if code:
            wc = norm_code(code)
        else:
            if preset not in PRESET_TITLES:
                raise ValueError("Choose a world type.")
            args = ["world-code", "--preset", preset]
            if seed not in (None, ""):
                s = str(seed).strip()
                if not s.isdigit() or int(s) > SEED_MAX:
                    raise ValueError("The seed must be a whole number from 0 to 18446744073709551615 (or empty for a random one).")
                args += ["--seed", str(int(s))]
            rc, out, err = run_cli(gen, args, timeout=60, runner=self.runner)
            data = parse_json(out) if rc == 0 else None
            if not isinstance(data, dict) or not data.get("code"):
                raise ValueError("Random New World could not make a code: " + _error_text(out, err))
            wc = norm_code(data["code"])
        specs = decode_code(wc)
        self._need_space()
        argv = check_args(["world", wc, "--install"])
        root = self.app.game_root
        if root and not BAD_PATH.search(str(root)):
            argv += ["--game-dir", str(root)]   # a path with cmd.exe's special characters is left out; RNW then finds the game itself
        if self.jobs.busy():
            raise ValueError("Random New World is already working on something. Wait for it to finish, or cancel it.")
        self.records.put(wc, {"preset": specs["preset"], "seed": str(specs["seed"]), "generator": specs["generator"],
                              "changes": specs["changes"], "requested_at": int(time.time()), "state": "running",
                              "how": "made by this app", "game_version": self.app.game_version})
        job = self.jobs.start("new", f"Making {PRESET_TITLES.get(specs['preset'], specs['preset'])} (seed {specs['seed']})",
                              gen.argv(argv), gen.folder, self._finish(wc, specs, "made by this app"))
        gamelog.log(self.app.game.id, f"Random New World: making {wc}")
        return {"job": job, "code": wc}

    def add_world(self, world_id):
        gen = self._need_cli()
        wid = check_args([str(world_id)])[0]
        self._need_space()
        job = self.jobs.start("add", f"Adding {wid} to the game", gen.argv(["add-world", wid]), gen.folder,
                              self._finish(None, None, "added by this app"))
        return {"job": job}

    def remove_world(self, world_id):
        """Take a world's mod out of the game (RNW keeps its library record, code and pictures)."""
        gen = self._need_cli()
        wid = check_args([str(world_id)])[0]
        rc, out, err = run_cli(gen, ["remove-world", wid], timeout=300, runner=self.runner)
        if rc != 0:
            raise ValueError("Random New World could not remove it: " + _error_text(out, err))
        self._rescan()
        return {"removed": wid}

    def cancel(self):
        return self.jobs.cancel()

    def _finish(self, code, specs, how):
        def done(job):
            ok = job["state"] == "done"
            res = job["result"] if isinstance(job["result"], dict) else {}
            if code is None:   # add-world: the world's id was in the command; the code comes from the result when it has one
                return self._after(job, ok)
            rec = {"state": job["state"], "finished_at": int(time.time()), "seconds": res.get("seconds") or job["finished"] - job["started"],
                   "how": how, "installed": str(res.get("installed") or ""), "error": job["error"]}
            if isinstance(res.get("summary"), (dict, list)):
                rec["summary"] = res["summary"]
            self.records.put(code, rec)
            gamelog.log(self.app.game.id, f"Random New World: {code} {job['state']}" + (f" ({job['error']})" if job["error"] else ""))
            self._after(job, ok, str(res.get("installed") or ""))
        return done

    def _after(self, job, ok, installed=""):
        if not ok:
            return
        self._rescan()
        mod = Path(self.app.user_dir or "") / "mod"
        if installed and Path(installed).parent != mod:
            job["error"] = job["error"] or (f"Random New World installed the world into {installed}, which is not the mod folder this app reads "
                                            f"({mod}). Check the folders in Settings.")

    def _rescan(self):
        mods = self.app.read_mods()
        with (self.app.state_lock or self.app.lock):
            self.app.apply_mods(mods)

    # -- playset --
    def use(self, pid, folder, on=True):
        """Turn one world on in a playset (and the others, and the generator hub, off), or turn it off.
        -> {"playset", "did": [text]}"""
        app = self.app
        ps = app.store.get(pid)
        mid = next((m for m, d in app.mods.items() if Path(d.get("root") or "").name == folder and is_world(d)), None)
        if mid is None:
            raise ValueError("That world is not in your mod folder yet. Press Add to game first.")
        name = app.mods[mid]["name"]
        mods, disabled, did = list(ps["mods"]), set(ps["disabled"]), []
        if not on:
            if mid in mods and mid not in disabled:
                disabled.add(mid)
                did.append(f"Turned {name} off.")
            return {"playset": app.update(pid, {"disabled": [m for m in mods if m in disabled]}) if did else ps, "did": did}
        for m, d in app.mods.items():
            if m != mid and (is_world(d) or is_hub(d)) and m in mods and m not in disabled:
                disabled.add(m)
                did.append(f"Turned {d['name']} off ({'the generator itself' if is_hub(d) else 'only one world can be on'}).")
        if mid in mods:
            mods.remove(mid)
        else:
            did.append(f"Added {name} to the playset.")
        mods.append(mid)
        if mid in disabled:
            disabled.discard(mid)
            did.append(f"Turned {name} on.")
        for r in order.missing_required(app.mods, [mid]):
            if r not in mods:
                mods.insert(max(0, len(mods) - 1), r)
                did.append(f"Added {app.mods[r]['name']}, which {name} needs.")
        did.append(f"{name} now loads last. Start a NEW 1337 campaign with it, and restart the game if another world was loaded before.")
        return {"playset": app.update(pid, {"mods": mods, "disabled": [m for m in mods if m in disabled]}), "did": did}


def is_world(m):
    return Path(m.get("root") or "").name.startswith(WORLD_PREFIX)


def is_hub(m):
    return Path(m.get("root") or "").name == HUB_FOLDER or str(m.get("remote_id") or "") == WORKSHOP_ID


def _free_gb(path):
    try:
        return round(shutil.disk_usage(str(path)).free / 1024 ** 3, 1) if path and Path(path).exists() else None
    except OSError:
        return None
