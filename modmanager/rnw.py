"""Random New World (beta), for Europa Universalis V only.

Random New World (RNW, https://github.com/Sir-Starch/eu5-random-new-world, MPL-2.0, Steam Workshop item 3829217331) is a
separate program that builds a new map for EU5. Every world it makes is an ordinary mod, a folder `rnw_exp_world_<id>` in
the game's `mod` folder. This module does not contain or copy RNW. It does not search the disk for it: the user points to the folder (check_folder),
which is looked at, and the user is told what was found. Then it starts the generator
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

from . import gamelog, order, pickfolder
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
RUN_OUTPUT_CAP = 8 * 1024 * 1024   # most output kept from one quick command
KILL_GRACE = 5  # seconds to wait for the output after killing a program that ran out of time
NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)
ARG_OK = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:\-]{0,299}$")
OPT_OK = re.compile(r"^--[a-z][a-z\-]{0,30}$")
BAD_PATH = re.compile(r'[%^&|<>"!\x00-\x1f]')   # characters cmd.exe treats specially, even in a quoted .cmd argument
CODE_IN_TEXT = re.compile(r"RNW1(?:-[A-Za-z0-9]+)+", re.I)
PROGRESS = re.compile(r"^\[\s*(\d+)%\]\s*(start|done)?\s*(.*)$")
SEARCH_DEPTH, SEARCH_CAP, SEARCH_SECONDS = 8, 60000, 10   # how far a search of the folder the user chose goes (levels, entries, seconds)
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
        # On Windows the window program (a windowed .exe) prints nothing to a pipe and can sit open for ever when given
        # --cli (seen on a real PC: the list took 214 s until the app was closed), so commands need rnw.cmd there.
        # Only the Linux package takes --cli on its single program.
        return bool(self.prefix or self.cmd or (self.launcher and os.name != "nt"))

    def argv(self, args):
        if self.prefix:
            base = list(self.prefix)
        elif self.cmd:
            base = [str(self.cmd)]
        elif self.launcher and os.name != "nt":
            base = [str(self.launcher), "--cli"]   # the window program also takes --cli (docs/generator-guide.md)
        else:
            raise ValueError("Random New World's command line (rnw.cmd) was not found in " + str(self.folder))
        return base + list(args)

    def public(self):
        return {"folder": str(self.folder), "cmd": str(self.cmd or ""), "launcher": str(self.launcher or ""), "how": self.how,
                "can_open": bool(self.launcher), "can_run": self.can_run}


def _walk(folder, depth=3, cap=4000, seconds=None, stats=None):
    """Every file in a folder and the folders inside it, level by level. Stops after `cap` entries, or `seconds`, so a search
    can never run for long. `stats` (a dict) gets the number of folders and entries looked at."""
    todo, seen = [(Path(folder), 0)], 0
    end = time.monotonic() + seconds if seconds else None
    while todo:
        d, lvl = todo.pop(0)
        if stats is not None:
            stats["folders"] = stats.get("folders", 0) + 1
        if end and time.monotonic() > end:
            return
        try:
            with os.scandir(d) as it:
                for e in it:
                    seen += 1
                    if stats is not None:
                        stats["entries"] = seen
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


def inspect_folder(folder, how="", depth=3, cap=4000, seconds=None, stats=None):
    """-> Generator or None: does this folder hold Random New World (rnw.cmd and/or its launcher)?"""
    folder = Path(folder)
    if folder.is_file():
        folder = folder.parent
    if not folder.is_dir():
        return None
    cmd = launcher = None
    for f in _walk(folder, depth, cap, seconds, stats):
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


def run_safely(argv, timeout, cwd):
    """subprocess.run with a timeout that really ends. On Windows, subprocess.run only kills the first process (cmd.exe) when the
    time is up; the program cmd.exe started keeps the output pipe open, so the second wait never returns and the page loads
    for ever. This kills the whole process tree. The output goes to temporary files, not pipes, so there is no pipe a stray
    child could hold open (closing or reading a pipe that another thread is blocked on hangs on Windows), and nothing waits
    for the output: only for the program itself.
    The program gets no keyboard input (stdin is empty), so it can never wait for someone to type. -> (code, out, err)"""
    import tempfile
    with tempfile.TemporaryFile() as fout, tempfile.TemporaryFile() as ferr:
        proc = subprocess.Popen(argv, stdin=subprocess.DEVNULL, stdout=fout, stderr=ferr, cwd=str(cwd), creationflags=NO_WINDOW)
        try:
            proc.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            _kill_tree(proc)
            try:
                proc.wait(timeout=KILL_GRACE)
            except Exception:
                pass
            raise subprocess.TimeoutExpired(argv, timeout)

        def text(f):
            f.seek(0)
            return f.read(RUN_OUTPUT_CAP).decode("utf-8", "replace")
        return proc.returncode, text(fout), text(ferr)


def run_cli(gen, args, timeout=60, runner=None):
    """One quick command of the generator. Arguments are checked first (a .cmd file runs through cmd.exe), and the
    command is started from an argument list, never a shell string. -> (exit code, text, error text)
    `runner` is for tests: a function like subprocess.run."""
    argv = gen.argv(check_args(args))
    if runner is None or runner is subprocess.run:
        return run_safely(argv, timeout, gen.folder)
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


RNWORLD_EXT = ".rnworld"
RNWORLD_LIMITS = {"rnworld.json": 64 * 1024, "world.json": 2 * 1024 * 1024}   # the pictures and the map atlas in the file are never read


def read_rnworld(source):
    """The world described by a .rnworld file. -> the dict stored in the file's world.json.
    A .rnworld file is what Random New World exports for one map ("the pure world"): a zip holding rnworld.json (kind "world",
    format 1, a hash of each file), world.json (code, preset, seed, generator, game build, the settings record, name, notes),
    atlas.json and atlas_labels.png (the map's picture data). It holds the recipe and a preview, not the 1.2 GB mod.
    Only the two small JSON files are read, each with a size limit; nothing is extracted to disk. Raises ValueError."""
    import zipfile
    try:
        z = zipfile.ZipFile(source)
    except (zipfile.BadZipFile, OSError):
        raise ValueError("That is not a Random New World map file: it is not a .rnworld archive.")
    with z:
        infos = {i.filename: i for i in z.infolist()}

        def read(name):
            i = infos.get(name)
            if i is None:
                raise ValueError(f"That file has no {name}, so it is not a map file from Random New World.")
            if i.file_size > RNWORLD_LIMITS[name]:
                raise ValueError(f"{name} in that file is far larger than a map file's, so it was not opened.")
            with z.open(i) as f:
                data = f.read(RNWORLD_LIMITS[name] + 1)
            if len(data) > RNWORLD_LIMITS[name]:
                raise ValueError(f"{name} in that file is far larger than a map file's, so it was not opened.")
            return data

        head_raw, body_raw = read("rnworld.json"), read("world.json")
        try:
            head, world = json.loads(head_raw.decode("utf-8")), json.loads(body_raw.decode("utf-8"))
        except ValueError:   # includes bad JSON and bad UTF-8
            raise ValueError("That map file is damaged: its description could not be read.")
        if not isinstance(head, dict) or head.get("kind") != "world":
            raise ValueError("That is a Random New World file, but not a single map (it says " + repr(str((head or {}).get("kind", "?")))[:40] + ").")
        if head.get("format") != 1:
            raise ValueError("That map file uses a newer format than this app knows. Update the app, or paste the map's world code instead.")
        want = (head.get("files") or {}).get("world.json") if isinstance(head.get("files"), dict) else None
        if want and want != hashlib.sha256(body_raw).hexdigest():
            raise ValueError("That map file is damaged (its checksum does not match).")
        if not isinstance(world, dict) or not world.get("code"):
            raise ValueError("That map file has no world code in it.")
        return world


ATLAS_LIMITS = {"atlas.json": 24 * 1024 * 1024, "atlas_labels.png": 48 * 1024 * 1024}
MAP_KEEP = 60   # most map files kept in the app's data folder (each is about 0.6 MB)
LOCATION_KINDS = {0: "land", 1: "wasteland", 2: "sea", 3: "lake"}


def map_key(code):
    return hashlib.sha256(str(code).encode("utf-8")).hexdigest()[:16]


class MapStore:
    """The map pictures of imported .rnworld files. A .rnworld holds atlas_labels.png (every pixel is the number of the location it
    belongs to, as red*65536+green*256+blue, minus 1; black is open sea) and atlas.json (what each location and country is). The
    page draws the map from those two. The file is copied into the app's data folder (`rnw-maps`, newest 60 kept) when it is
    imported, so the map is there even when the original file moves. Nothing here starts a program."""

    def __init__(self, folder):
        self.folder = Path(folder)

    def _path(self, key):
        if not re.fullmatch(r"[0-9a-f]{16}", str(key or "")):
            raise ValueError("Unknown map.")
        return self.folder / (key + RNWORLD_EXT)

    def save(self, code, src):
        key = map_key(code)
        self.folder.mkdir(parents=True, exist_ok=True)
        tmp = self.folder / (key + ".tmp")
        shutil.copyfile(src, tmp)
        os.replace(tmp, self._path(key))
        files = sorted(self.folder.glob("*" + RNWORLD_EXT), key=lambda f: f.stat().st_mtime, reverse=True)
        for old in files[MAP_KEEP:]:
            try:
                old.unlink()
            except OSError:
                pass
        return key

    def has(self, key):
        try:
            return self._path(key).is_file()
        except ValueError:
            return False

    def _member(self, key, name):
        import zipfile
        f = self._path(key)
        if not f.is_file():
            raise ValueError("That map file is no longer in the app's data folder. Import it again.")
        try:
            with zipfile.ZipFile(f) as z:
                i = z.getinfo(name)
                if i.file_size > ATLAS_LIMITS[name]:
                    raise ValueError(f"{name} is far larger than expected, so it was not opened.")
                with z.open(i) as h:
                    data = h.read(ATLAS_LIMITS[name] + 1)
        except KeyError:
            raise ValueError(f"The map file has no {name}.")
        except (zipfile.BadZipFile, OSError):
            raise ValueError("The saved map file could not be read.")
        if len(data) > ATLAS_LIMITS[name]:
            raise ValueError(f"{name} is far larger than expected, so it was not opened.")
        return data

    def png(self, key):
        data = self._member(key, "atlas_labels.png")
        if not data.startswith(b"\x89PNG\r\n\x1a\n"):
            raise ValueError("The map picture in that file is not a PNG.")
        return data

    def atlas(self, key):
        """What the page needs to draw the map and list what is on it: per-location columns, the countries, and a summary."""
        try:
            a = json.loads(self._member(key, "atlas.json").decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            raise ValueError("The map data in that file could not be read.")
        L = a.get("locations") if isinstance(a, dict) else None
        if not isinstance(L, dict) or not isinstance(L.get("kind"), list):
            raise ValueError("The map data in that file has a layout this app does not know.")
        n = len(L["kind"])
        cols = {}
        for k in ("kind", "owner", "topography", "vegetation", "climate", "culture", "religion", "population", "name"):
            v = L.get(k)
            if not isinstance(v, list) or len(v) != n:
                raise ValueError("The map data in that file has a layout this app does not know.")
            cols[k] = v
        cols["name"] = [(x[-1] if isinstance(x, list) and x else x) if isinstance(x, (str, list)) else "" for x in cols["name"]]
        countries = [{"name": str(c.get("name", ""))[:60], "tag": str(c.get("tag", ""))[:8], "kind": str(c.get("kind", "")),
                      "color": [int(x) & 255 for x in (c.get("color") or [128, 128, 128])[:3]], "locations": int(c.get("locations") or 0),
                      "culture": c.get("culture", -1), "religion": c.get("religion", -1)}
                     for c in (a.get("countries") or []) if isinstance(c, dict)]
        vocab = a.get("vocabulary") if isinstance(a.get("vocabulary"), dict) else {}
        return {"size": a.get("size"), "scale": a.get("scale"), "vocabulary": vocab, "countries": countries, "locations": cols,
                "summary": self._summary(cols, countries, vocab)}

    @staticmethod
    def _summary(cols, countries, vocab):
        """The characteristics of the map in numbers, for the list beside it."""
        kinds, pop = {}, [0] * len(countries)
        land = [i for i, k in enumerate(cols["kind"]) if k == 0]
        for k in cols["kind"]:
            kinds[LOCATION_KINDS.get(k, "other")] = kinds.get(LOCATION_KINDS.get(k, "other"), 0) + 1
        for i in land:
            o = cols["owner"][i]
            if isinstance(o, int) and 0 <= o < len(pop):
                pop[o] += int(cols["population"][i] or 0)

        def count(col, vname, only=land):
            names = vocab.get(vname) or []
            c = {}
            for i in only:
                v = cols[col][i]
                if isinstance(v, int) and 0 <= v < len(names):
                    c[names[v]] = c.get(names[v], 0) + 1
            return sorted(c.items(), key=lambda kv: -kv[1])
        settled = [i for i in land if cols["owner"][i] >= 0]
        by_size = sorted(range(len(countries)), key=lambda i: (-countries[i]["locations"], i))[:10]
        return {"locations": kinds, "countries": {"state": sum(1 for c in countries if c["kind"] == "state"), "tribe": sum(1 for c in countries if c["kind"] == "tribe")},
                "population": sum(int(cols["population"][i] or 0) for i in land), "settled_locations": len(settled),
                "topography": count("topography", "topography"), "vegetation": count("vegetation", "vegetation"), "climate": count("climate", "climate"),
                "cultures": count("culture", "culture", settled)[:12], "religions": count("religion", "religion", settled)[:12],
                "largest": [{"name": countries[i]["name"], "tag": countries[i]["tag"], "kind": countries[i]["kind"], "locations": countries[i]["locations"],
                             "population": pop[i]} for i in by_size]}


def entry(**kw):
    e = {"folder": "", "path": "", "installed": False, "id": "", "mod_id": "", "name": "", "tag": "", "code": "", "valid_code": False,
         "preset": "", "preset_title": "", "seed": "", "generator": "", "game_build": "", "created": 0, "seconds": 0,
         "changes": [], "details": [], "place": "", "notes": "", "starred": False, "parent": "", "part": "",
         "made_here": False, "how": "", "specs_from": [], "in_playset": "none", "problem": "", "map": ""}
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
            if rec.get("state") not in ("done", "imported"):
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
        if rec.get("map"):
            e["map"] = str(rec["map"])[:16]
        for k in ("name", "tag", "notes"):   # a map imported from a .rnworld file brings these with it
            if rec.get(k) and not e[k]:
                e[k] = str(rec[k])[:300 if k == "notes" else 80 if k == "name" else 8]
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

    def _new(self, kind, label):
        if self.job and self.job["state"] == "running":
            raise ValueError("Random New World is already working on something. Wait for it to finish, or cancel it.")
        self._n += 1
        job = self.job = {"id": self._n, "kind": kind, "label": label, "state": "running", "percent": 0, "stage": "Starting",
                          "log": [], "error": "", "result": None, "started": time.time(), "finished": 0, "cancel": False}
        return job

    def start(self, kind, label, argv, cwd, on_done=None):
        with self.lock:
            job = self._new(kind, label)
        threading.Thread(target=self._run, args=(job, argv, cwd, on_done), daemon=True, name="rnw-job").start()
        return self.public(job)

    def start_func(self, kind, label, fn, on_done=None):
        """A job that runs a Python function `fn(job)` (copying a world into the mod folder). The function updates
        job["percent"], job["stage"] and job["log"], stops when job["cancel"] is set, and returns the result."""
        with self.lock:
            job = self._new(kind, label)
        threading.Thread(target=self._run_func, args=(job, fn, on_done), daemon=True, name="rnw-job").start()
        return self.public(job)

    def _run_func(self, job, fn, on_done):
        try:
            job["result"] = fn(job)
            job["outcome"], job["percent"] = ("cancelled" if job["cancel"] else "done"), (job["percent"] if job["cancel"] else 100)
        except Exception as e:   # said on the page, in words
            job["outcome"], job["error"] = "failed", (str(e) if isinstance(e, (ValueError, OSError)) else f"{type(e).__name__}: {e}")[:300]
        finally:
            job["finished"] = time.time()
            if on_done:
                try:
                    on_done(job)
                except Exception as e:
                    job["error"] = job["error"] or f"The app could not finish: {e}"[:300]
            job["state"] = job.get("outcome") or "failed"

    def _run(self, job, argv, cwd, on_done):
        out, proc = [], None
        try:
            proc = self.proc = self.popen(argv, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding="utf-8",
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
            # The result is held in "outcome" and only becomes the visible "state" after on_done (the rescan) has run,
            # so a page that sees "done" always finds the new world already in the list.
            if job["cancel"]:
                job["outcome"] = "cancelled"
            elif rc == 0:
                job["outcome"], job["percent"] = "done", 100
                job["result"] = parse_json(text)
            else:
                job["outcome"], job["error"] = "failed", _error_text(text, "")
                job["rc"] = rc
        except Exception as e:   # the program could not start, or the pipe broke: say so on the page
            job["outcome"], job["error"] = "failed", f"{type(e).__name__}: {e}"[:300]
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
            job["state"] = job.get("outcome") or "failed"

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

    def __init__(self, app, runner=None, popen=subprocess.Popen, generator=None, picker=pickfolder.pick_folder):
        self.app = app
        self.runner, self.popen, self.picker = runner, popen, picker
        self.jobs = Jobs(popen)
        self._diag_sig = ""
        self._logged_start = False
        self._generator = generator            # tests hand in a stub; None = look on this PC
        self.records = Records(app.cfg / "rnw-worlds.json")
        self.maps = MapStore(app.cfg / "rnw-maps")

    # -- finding it --
    def generator(self):
        """The generator in the folder the USER pointed to (Settings key rnw_dir). The app does not search the disk for it:
        it asks the user for the folder, checks that folder and says what it found (check_folder)."""
        if self._generator is not None:
            return self._generator
        return find_generator(self.app.store.settings().get("rnw_dir", ""), [])

    def pick_folder(self, what, start=""):
        """Open the system's folder window for the user. what: 'generator' | 'map'. Waits for the choice, so the request
        that calls this must not hold the data lock."""
        if what == "file":
            return self.picker("Choose a Random New World map file (.rnworld)", start, kind="file")
        title = "Choose the folder where Random New World is installed (the one with rnw.cmd)" if what == "generator" \
            else "Choose the folder of a Random New World map (rnw_exp_world_…), or a folder that holds several"
        return self.picker(title, start)

    def check_folder(self, path):
        """The user pointed to a folder: look in it (three levels down at most), say what was found and what is missing, and
        remember the folder when it holds Random New World. -> {"ok", "generator", "report": [{"ok", "text"}]}"""
        path = str(path or "").strip().strip('"')
        if not path:   # an empty answer forgets the folder
            self.app.store.update_settings(rnw_dir="")
            return {"ok": False, "generator": None, "report": [{"ok": True, "text": "Forgot the folder. Point to it again when you want to make maps."}]}
        if any(ord(c) < 32 for c in path):
            raise ValueError("That is not a folder path.")
        folder = Path(path)
        report = []
        if not folder.is_dir():
            return {"ok": False, "generator": None, "report": [{"ok": False, "text": f"{path} is not a folder on this PC. Check the spelling, "
                                                                                 "or copy the folder's path from Explorer (Shift + right-click, Copy as path)."}]}
        stats = {}
        gen = inspect_folder(folder, "the folder you chose", depth=SEARCH_DEPTH, cap=SEARCH_CAP, seconds=SEARCH_SECONDS, stats=stats)
        report.append({"ok": True, "text": f"Searched {folder} and every folder inside it for rnw.cmd and the Random New World program "
                                           f"({stats.get('folders', 0):,} folders looked at)."})
        if gen is None or not gen.cmd:   # rnw.cmd was not inside: look in the two folders above it (the user may have chosen a folder inside the package)
            up = folder
            for _ in range(2):
                up = up.parent
                if len(up.parts) <= 2:   # a drive's top folder or the home folder is far too big to search
                    break
                stats2 = {}
                near = inspect_folder(up, "a folder above the one you chose", depth=4, cap=SEARCH_CAP // 2, seconds=SEARCH_SECONDS // 2, stats=stats2)
                if near and near.cmd:
                    report.append({"ok": True, "text": f"rnw.cmd was not in that folder, so I also searched the folder above it, {up} "
                                                       f"({stats2.get('folders', 0):,} folders looked at), and found it there."})
                    gen = near
                    break
                report.append({"ok": False, "text": f"rnw.cmd was not in that folder, and not in the folder above it, {up} ({stats2.get('folders', 0):,} folders looked at)."})
        if gen is None:
            report.append({"ok": False, "text": "Random New World was not found there: no rnw.cmd and no Random New World program. "
                                                "Point to the folder that holds them."})
            return {"ok": False, "generator": None, "report": report}
        report.append({"ok": bool(gen.cmd), "text": f"Command line (rnw.cmd): {gen.cmd}" if gen.cmd else "Command line (rnw.cmd): not found."})
        report.append({"ok": bool(gen.launcher), "text": f"Window program: {gen.launcher.name}" if gen.launcher else "Window program: not found."})
        if gen.can_run:
            report.append({"ok": True, "text": "Ready: maps can be made from here."})
        else:
            report.append({"ok": False, "text": "Maps cannot be made from here: rnw.cmd was not found" + (", but the window can be opened"
                           if gen.launcher else "") + ". You can still import maps you already have."})
        self.app.store.update_settings(rnw_dir=str(gen.folder))
        self._generator = None
        gamelog.log(self.app.game.id, "Random New World folder chosen: " + " | ".join(r["text"] for r in report))
        return {"ok": gen.can_run, "generator": gen.public(), "report": report}

    # -- listing --
    def list_job(self, use_cli=True):
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
            if gen and gen.can_run and use_cli:
                started = time.time()
                if not self._logged_start:   # LOG-CHECK: a "started" line without a "finished" line after it means the command hung
                    self._logged_start = True
                    gamelog.log(self.app.game.id, "Random New World worlds command started: " + " ".join(gen.argv(["worlds"])))
                try:
                    rc, out, err = run_cli(gen, ["worlds"], timeout=25, runner=self.runner)
                    gamelog.log(self.app.game.id, f"Random New World worlds command finished in {time.time() - started:.1f} s, "
                                f"exit code {rc}, {len(out)} characters out, first: {out.strip()[:200]!r}, errors: {err.strip()[-200:]!r}")
                    data = parse_json(out) if rc == 0 else None
                    if isinstance(data, list):
                        library, cli["ok"] = data, True
                    else:
                        cli["error"] = _error_text(out, err) if rc else "The generator's list of worlds could not be read."
                except (OSError, subprocess.SubprocessError) as e:
                    cli["error"] = f"{type(e).__name__}: {e}"[:300]
                    gamelog.log(self.app.game.id, f"Random New World worlds command failed after {time.time() - started:.1f} s: {cli['error']}")
            worlds = merge_worlds(installed, library, self.records.load(), mod_ids)
            self._diag(gen, cli, library, installed, worlds)
            for w in worlds:
                if w["map"] and not self.maps.has(w["map"]):   # the app's copy is gone: do not offer a map that cannot open
                    w["map"] = ""
                    w["map_lost"] = True
                mid = w["mod_id"]
                w["in_playset"] = "none" if not mid or mid not in inlist else "on" if mid in enabled else "off"
            if gen is None:
                notes.append("Random New World was not found yet. Under Make a new map, press Browse… and choose the folder where it is installed.")
            elif not use_cli:
                pass   # the page asked for the files only: no program is started, nothing is said about the generator's list
            elif not gen.can_run:
                notes.append("Random New World's window program was found, but not its command line (rnw.cmd), so maps cannot be made from "
                             "here. You can still open the generator and import maps you already have.")
            elif not cli["ok"]:
                notes.append("The generator's own list of worlds could not be read, so only worlds installed in your mod folder "
                             "are shown. " + cli["error"])
            return {"generator": gen.public() if gen else None, "worlds": worlds, "cli": cli, "cli_used": bool(use_cli and gen and gen.can_run), "notes": notes, "presets": PRESETS,
                    "hub": {"installed": bool(hub), "enabled": any(h in enabled for h in hub)}, "playset": pid,
                    "game_version": version, "job": job, "free_gb": _free_gb(user_dir), "user_dir": str(user_dir or "")}
        return run

    def _diag(self, gen, cli, library, installed, worlds):
        """Write what a real PC showed us to the app log, once per change (not on every page load), so one log is enough to
        check the guesses listed in docs/25. LOG-CHECK: what a good log shows is described next to each line."""
        lib_keys = sorted(library[0]) if library and isinstance(library[0], dict) else []
        places = {}
        for w in library:
            if isinstance(w, dict):
                places[str(w.get("place"))] = places.get(str(w.get("place")), 0) + 1
        bad = ["%s: %s" % (w["folder"], w["problem"]) for w in worlds if w.get("problem")]
        listing = []
        if gen:   # LOG-CHECK: what is in the generator's folder (two levels), to see where rnw.cmd is, if anywhere
            try:
                for a in sorted(os.listdir(gen.folder))[:40]:
                    pa = gen.folder / a
                    listing.append(a + ("/" if pa.is_dir() else ""))
                    if pa.is_dir():
                        listing += ["  " + a + "/" + b for b in sorted(os.listdir(pa))[:12]]
            except OSError as e:
                listing.append(f"could not list: {e}")
        lines = [
            f"generator folder holds: {listing[:80]}",
            # good: a folder that holds rnw.cmd (and a launcher .exe); "how" says where it was found
            f"generator: {gen.public() if gen else None}",
            # good: ok True; library = the number of worlds RNW itself lists; keys should include id, code, preset, seed, place
            f"worlds command: ok={cli['ok']} error={cli['error']!r} library={len(library)} keys={lib_keys} places={places}",
            # good: installed = the rnw_exp_world_* folders read here; each should carry a receipt (world.json) and a code
            f"in the mod folder: {len(installed)} worlds, with receipt {sum(1 for e in installed if e.get('id'))}, "
            f"with code {sum(1 for e in installed if e.get('code'))}",
            # good: empty. Anything here is a world code this app could not decode (the format guess may be wrong)
            f"codes that did not decode: {bad[:5]}",
        ]
        sig = "\n".join(lines)
        if sig != self._diag_sig:
            self._diag_sig = sig
            for line in lines:
                gamelog.log(self.app.game.id, "Random New World " + line)

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

    # -- importing worlds you already have --
    def import_code(self, code):
        """Remember a world code (nothing is built): the page then lists the world with the settings decoded from the code."""
        wc = norm_code(code)
        specs = decode_code(wc)
        self.records.put(wc, {"preset": specs["preset"], "seed": str(specs["seed"]), "generator": specs["generator"],
                              "changes": specs["changes"], "requested_at": int(time.time()), "state": "imported",
                              "how": "imported by this app"})
        gamelog.log(self.app.game.id, f"Random New World: imported the code {wc}")
        return {"code": wc, "preset": specs["preset"], "seed": str(specs["seed"])}

    def import_rnworld(self, path, label=None):
        """Import one .rnworld file: remember the map's world code with everything the file says about it (nothing is built
        and nothing is copied into the mod folder). The page then lists it with its settings."""
        src = Path(str(path))
        if src.is_symlink() or not src.is_file():
            raise ValueError("That is not a file on this PC.")
        w = read_rnworld(src)
        try:
            wc = norm_code(w["code"])
            specs = decode_code(wc)
        except CodeError as e:
            raise ValueError("The world code in that file is not valid: " + str(e))
        created = w.get("created")
        rec = {"state": "imported", "preset": specs["preset"], "seed": str(specs["seed"]), "generator": specs["generator"],
               "changes": specs["changes"], "requested_at": int(created) if isinstance(created, (int, float)) and created > 0 else int(time.time()),
               "how": "imported from a .rnworld file", "name": str(w.get("name") or "")[:80], "tag": str(w.get("user_tag") or w.get("tag") or "")[:8],
               "notes": str(w.get("notes") or "")[:300]}
        if w.get("game_build"):
            rec["game_version"] = str(w["game_build"])[:40]
        if isinstance(w.get("seconds"), (int, float)):
            rec["seconds"] = w["seconds"]
        if isinstance(w.get("record"), dict):
            rec["summary"] = w["record"]
        try:   # the map's picture and data are kept so the page can draw the map
            rec["map"] = self.maps.save(wc, src)
        except OSError as e:
            gamelog.log(self.app.game.id, f"Random New World: could not keep the map picture of {label or src.name}: {e}")
        self.records.put(wc, rec)
        gamelog.log(self.app.game.id, f"Random New World: imported the map file {label or src.name} ({wc[:20]}…, {specs['preset']}, seed {specs['seed']})")
        return {"code": wc, "preset": specs["preset"], "seed": str(specs["seed"]), "file": label or src.name}

    def import_any(self, path):
        """What the user typed or chose in the import box: a .rnworld file, a folder holding .rnworld files, or a map folder
        (or a folder of map folders). -> {"worlds": [...]} done at once, or {"job": ...} for a copy that runs in the background."""
        p = str(path or "").strip().strip('"')
        if not p or any(ord(c) < 32 for c in p):
            raise ValueError("Give a map file (.rnworld) or the folder of a map (the one named like rnw_exp_world_...).")
        src = Path(p)
        if src.suffix.lower() == RNWORLD_EXT:
            return {"worlds": [self.import_rnworld(src)]}
        try:
            if src.is_dir() and not src.is_symlink() and not read_world_folder(src):
                kids = sorted(src.iterdir())
                files = [f for f in kids if f.suffix.lower() == RNWORLD_EXT and f.is_file() and not f.is_symlink()]
                if files and not any(d.is_dir() and not d.is_symlink() and read_world_folder(d) for d in kids):
                    return {"worlds": [self.import_rnworld(f) for f in files[:200]]}
        except OSError:
            pass   # import_folder says what is wrong with the folder
        return {"job": self.import_folder(p)}

    def import_folder(self, path):
        """Copy world mod folder(s) into the mod folder. `path` is one world (rnw_exp_world_...) or a folder holding several.
        Runs in the background (a world is about 1.2 GB) and never overwrites a world that is already there."""
        path = str(path or "").strip().strip('"')
        if not path or any(ord(c) < 32 for c in path):
            raise ValueError("Give the folder of a world (the one named like rnw_exp_world_...).")
        src = Path(path)
        mod = Path(self.app.user_dir or "") / "mod"
        if not self.app.user_dir or not mod.is_dir():
            raise ValueError("The game's mod folder was not found, so there is nowhere to put the world. Check the folders in Settings.")
        if src.is_symlink() or not src.is_dir():
            raise ValueError("That is not a folder on this PC.")
        if src.resolve() == mod.resolve() or mod.resolve() in src.resolve().parents:
            raise ValueError("That folder is already inside your mod folder.")
        worlds = [src] if read_world_folder(src) else []
        if not worlds:   # a folder that holds several worlds
            try:
                worlds = [d for d in sorted(src.iterdir()) if d.is_dir() and not d.is_symlink() and read_world_folder(d)]
            except OSError as e:
                raise ValueError(f"That folder could not be read: {e.strerror or e}")
        if not worlds:
            raise ValueError("No Random New World map was found there. A map is a folder named like rnw_exp_world_abcde23456 "
                             "with a .metadata folder inside; pick that folder, or the folder that holds several of them.")
        todo = [w for w in worlds if not (mod / w.name).exists()]
        if not todo:
            raise ValueError("Those worlds are already in your mod folder.")
        names = [w.name for w in todo]

        def work(job):
            sizes = {}
            job["stage"] = "Measuring"
            for w in todo:
                files = []
                for root, dirs, fs in os.walk(w):
                    dirs[:] = [d for d in dirs if not os.path.islink(os.path.join(root, d))]
                    files += [os.path.join(root, f) for f in fs if not os.path.islink(os.path.join(root, f))]
                sizes[w] = files
            total = sum(os.path.getsize(f) for fl in sizes.values() for f in fl) or 1
            free = _free_gb(self.app.user_dir)
            if free is not None and free * 1024 ** 3 < total * 1.05:
                raise ValueError(f"Not enough free disk space: {total / 1024 ** 3:.1f} GB are needed, {free:.1f} GB are free.")
            job["log"].append(f"{len(todo)} world(s), {total / 1024 ** 3:.2f} GB, copying into {mod}")
            done = 0
            for w in todo:
                job["stage"] = f"Copying {w.name}"
                tmp = mod / (w.name + ".importing")   # copied under another name and renamed at the end: no half world is ever seen
                shutil.rmtree(tmp, ignore_errors=True)
                try:
                    for f in sizes[w]:
                        if job["cancel"]:
                            raise InterruptedError
                        dest = tmp / os.path.relpath(f, w)
                        dest.parent.mkdir(parents=True, exist_ok=True)
                        shutil.copyfile(f, dest)
                        done += os.path.getsize(f)
                        job["percent"] = min(99, int(done * 100 / total))
                    if not sizes[w]:
                        tmp.mkdir(parents=True, exist_ok=True)
                    os.replace(tmp, mod / w.name)
                    job["log"].append("copied " + w.name)
                except BaseException:
                    shutil.rmtree(tmp, ignore_errors=True)
                    if job["cancel"]:
                        return {"imported": []}
                    raise
            return {"imported": names}

        def done(job):
            if job.get("outcome") == "done":
                self._rescan()
            gamelog.log(self.app.game.id, f"Random New World: import of {names} {job.get('outcome')}" + (f" ({job['error']})" if job["error"] else ""))
        gamelog.log(self.app.game.id, f"Random New World: importing {names} from {src}")
        return self.jobs.start_func("import", f"Importing {len(todo)} world(s)" if len(todo) > 1 else f"Importing {names[0]}", work, done)

    def cancel(self):
        return self.jobs.cancel()

    def _finish(self, code, specs, how):
        def done(job):
            ok = job.get("outcome") == "done"
            res = job["result"] if isinstance(job["result"], dict) else {}
            if code is None:   # add-world: the world's id was in the command; the code comes from the result when it has one
                return self._after(job, ok)
            rec = {"state": job.get("outcome") or "failed", "finished_at": int(time.time()), "seconds": res.get("seconds") or job["finished"] - job["started"],
                   "how": how, "installed": str(res.get("installed") or ""), "error": job["error"]}
            if isinstance(res.get("summary"), (dict, list)):
                rec["summary"] = res["summary"]
            self.records.put(code, rec)
            if not ok:   # LOG-CHECK: the program's own last lines, to compare with what a good run prints
                gamelog.log(self.app.game.id, f"Random New World exit code {job.get('rc')}, last lines: " + " | ".join(job["log"][-6:])[:600])
            gamelog.log(self.app.game.id, f"Random New World: {code} {job.get('outcome')}" + (f" ({job['error']})" if job["error"] else ""))
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
