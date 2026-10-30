"""Discover installed mods and analyse files/definitions/localization for conflicts."""
import json
import os
import re
from collections import defaultdict
import xml.etree.ElementTree as ET
from pathlib import Path

from .descriptor import META_PATHS, parse_descriptor, parse_metadata

SKIP_TOP = {".metadata", "metadata", ".git"}
SKIP_ROOT_FILES = {"descriptor.mod", "metadata.json", "thumbnail.png", "thumbnail.jpg", "readme.md",
                   "readme.txt", "license", "license.md", "changelog.md"}
DEFAULT_DEF_DIRS = ("common", "events")  # script folders where top-level keys are definitions
PATCH_PREFIX = re.compile(r"^(REPLACE_OR_CREATE|TRY_REPLACE|REPLACE|INJECT_OR_CREATE|TRY_INJECT|INJECT):(.+)$")
LOC_LINE = re.compile(r"^\s*([A-Za-z0-9_.'\-]+):\d*\s+\"")
LOC_LANG = re.compile(r"^\s*(l_[a-z_]+):")
MAX_PER_KIND = 500
VANILLA = "__vanilla__"  # pseudo-mod id for the base game when comparing against it


def _isdir(p):
    """is_dir() that says False instead of raising: Windows reports some links and mounts (WinError 448, 'untrusted
    mount point', and similar) as errors, and one such folder must not stop the whole mod list from loading."""
    try:
        return Path(p).is_dir()
    except OSError:
        return False


def _isfile(p):
    try:
        return Path(p).is_file()
    except OSError:
        return False


def _exists(p):
    try:
        return Path(p).exists()
    except OSError:
        return False


def _read(p):
    return Path(p).read_text(encoding="utf-8-sig", errors="replace")


def _meta_file(root):
    for rel in META_PATHS:
        f = Path(root) / rel
        if _isfile(f):
            return f
    return None


def looks_like_mod(d):
    return _meta_file(d) is not None or _isfile(Path(d) / "descriptor.mod")


def _load_desc(desc_file, root):
    """Merge a .mod descriptor with the mod's metadata.json (metadata wins)."""
    desc = parse_descriptor(_read(desc_file)) if desc_file else {}
    mf = _meta_file(root) if root else None
    if mf:
        text = _read(mf)
        try:
            ok = isinstance(json.loads(text), dict)
        except ValueError:
            ok = False
        if not ok:
            desc["error"] = f"{mf.name} is unreadable (not valid JSON)"
        for k, v in parse_metadata(text).items():
            if v not in ("", [], {}, None):
                desc[k] = v
    return desc


def _mod_root(desc_file, desc):
    p = desc.get("path") or desc.get("archive")
    if not p:
        return None
    path = Path(p)
    if not path.is_absolute():
        path = desc_file.parent.parent / p
    return path


def scan_mods(user_dir=None, workshop_dir=None):
    """Return {mod_id: info}. mod_id is 'ws:<id>' or 'local:<name>'. An entry that cannot be read is skipped."""
    mods = {}
    if workshop_dir and _isdir(workshop_dir):
        def workshop_mod(d):
            try:
                if _isdir(d) and looks_like_mod(d):
                    df = d / "descriptor.mod"
                    desc = _load_desc(df if _isfile(df) else None, d)
                    return f"ws:{d.name}", _info(f"ws:{d.name}", desc, d, "workshop", d.name)
            except OSError:
                pass
            return None
        for found in _adaptive_map(workshop_mod, _listdir(workshop_dir), 0.002):   # several file checks per mod: slow disks use threads
            if found:
                mods[found[0]] = found[1]
    if user_dir and _isdir(Path(user_dir) / "mod"):
        mod_dir = Path(user_dir) / "mod"
        for f in [x for x in _listdir(mod_dir) if x.suffix == ".mod"]:
            try:
                desc = parse_descriptor(_read(f))
                rid = desc.get("remote_file_id")
                root = _mod_root(f, desc)
                mid = f"ws:{rid}" if rid and f"ws:{rid}" in mods else f"local:{f.stem}"
                if mid in mods:  # descriptor stub for a workshop mod we already found
                    continue
                mods[mid] = _info(mid, _load_desc(f, root), root, "local", rid)
            except OSError:
                continue
        for d in _listdir(mod_dir):  # bare folders with their own metadata
            try:
                if _isdir(d) and looks_like_mod(d) and not any(m["root"] == str(d) for m in mods.values()):
                    df = d / "descriptor.mod"
                    mid = f"local:{d.name}"
                    mods.setdefault(mid, _info(mid, _load_desc(df if _isfile(df) else None, d), d, "local", None))
            except OSError:
                continue
    return mods


def _listdir(d):
    try:
        return sorted(Path(d).iterdir())
    except OSError:
        return []


# ---- Bannerlord-style modules: a folder with SubModule.xml ----
OFFICIAL_MODULES = ("Native", "SandBoxCore", "CustomBattle", "Sandbox", "StoryMode", "BirthAndDeath", "NavalDLC", "Multiplayer")
MAX_SUBMODULE = 1024 * 1024


def parse_submodule(text):
    """SubModule.xml -> dict of what the load order needs, or None if it is not a module description. Never raises.
    Documents with a DOCTYPE or entities are refused (nothing legitimate needs them)."""
    if len(text) > MAX_SUBMODULE or "<!DOCTYPE" in text.upper() or "<!ENTITY" in text.upper():
        return None
    try:
        root = ET.fromstring(text.lstrip("\ufeff"))
    except ET.ParseError:
        return None
    if root.tag != "Module":
        return None
    val = lambda tag: (root.find(tag).get("value") or "").strip() if root.find(tag) is not None else ""
    mid = val("Id")
    if not re.fullmatch(r"[A-Za-z0-9_.\-]{1,100}", mid):  # it goes onto the game's command line: letters, digits and _ . - only
        return None
    before_hard, before_soft, after_soft, incompatible = [], [], [], []
    for e in root.findall("./DependedModules/DependedModule"):
        i = (e.get("Id") or "").strip()
        if i:
            (before_soft if (e.get("Optional") or "").lower() == "true" else before_hard).append(i)
    for e in root.findall("./DependedModules/OptionalDependModule") + root.findall("./OptionalDependModules/*"):
        i = (e.get("Id") or "").strip()
        if i:
            before_soft.append(i)
    for e in root.findall("./DependedModuleMetadatas/DependedModuleMetadata"):
        i = (e.get("id") or "").strip()
        if not i:
            continue
        optional = (e.get("optional") or "").lower() == "true"
        if (e.get("incompatible") or "").lower() == "true":
            incompatible.append(i)
        elif e.get("order") == "LoadBeforeThis":
            (before_soft if optional else before_hard).append(i)
        elif e.get("order") == "LoadAfterThis":
            after_soft.append(i)
    for e in root.findall("./ModulesToLoadAfterThis/Module"):
        if (e.get("Id") or "").strip():
            after_soft.append(e.get("Id").strip())
    for e in root.findall("./IncompatibleModules/Module"):
        if (e.get("Id") or "").strip():
            incompatible.append(e.get("Id").strip())
    uniq = lambda xs: list(dict.fromkeys(xs))
    hard = uniq(before_hard)
    return {"id": mid, "name": val("Name") or mid, "version": val("Version"),
            "official": val("Official").lower() == "true" or mid in OFFICIAL_MODULES,
            "dependencies": hard, "load_after": [i for i in uniq(before_soft) if i not in hard],
            "load_before": uniq(after_soft), "incompatible": uniq(incompatible), "url": val("Url")}


def _module_info(mid_key, sub, root, source, remote_id):
    info = _info(mid_key, {"name": sub["name"], "version": sub["version"], "dependencies": sub["dependencies"],
                           "dependency_ids": {d: d for d in sub["dependencies"]}, "incompatible": sub["incompatible"],
                           "meta_id": sub["id"]}, root, source, remote_id)
    info.update({"load_after": sub["load_after"], "load_before": sub["load_before"], "official": sub["official"],
                 "rank": 0 if sub["official"] else 1, "url": sub["url"]})
    return info


def _workshop_mark(d):
    """The Workshop id of a Modules copy the app installed from a steamcmd download (install.WORKSHOP_MARK), else None."""
    try:
        wid = _read(d / ".ronin-workshop-id").strip()
    except OSError:
        return None
    return wid if re.fullmatch(r"\d{1,20}", wid) else None


def scan_modules(game_root, workshop_dir=None):
    """Modules of a Bannerlord-style game: <install>/Modules/<x>/SubModule.xml first, then the Workshop folder (each item
    folder is itself a module). A module id found twice keeps its first copy, like the game does."""
    mods, seen = {}, set()
    if game_root and _isdir(Path(game_root) / "Modules"):
        for d in _listdir(Path(game_root) / "Modules"):
            try:
                sm = d / "SubModule.xml"
                if not (_isdir(d) and _isfile(sm)):
                    continue
                sub = parse_submodule(_read(sm))
                if sub and sub["id"] not in seen:
                    seen.add(sub["id"])
                    mods[f"local:{sub['id']}"] = _module_info(f"local:{sub['id']}", sub, d, "local", _workshop_mark(d))
            except OSError:
                continue
    if workshop_dir and _isdir(workshop_dir):
        for d in _listdir(workshop_dir):
            try:
                sm = d / "SubModule.xml"
                if not (_isdir(d) and _isfile(sm)):
                    continue
                sub = parse_submodule(_read(sm))
                if sub and sub["id"] not in seen:
                    seen.add(sub["id"])
                    mods[f"ws:{d.name}"] = _module_info(f"ws:{d.name}", sub, d, "workshop", d.name)
            except OSError:
                continue
    return mods


def _info(mid, desc, root, source, remote_id):
    return {
        "id": mid,
        "name": desc.get("name") or (Path(root).name if root else mid),
        "version": desc.get("version", ""),
        "supported_version": desc.get("supported_version", ""),
        "tags": desc.get("tags", []),
        "dependencies": desc.get("dependencies", []),
        "dependency_ids": desc.get("dependency_ids", {}),
        "incompatible": desc.get("incompatible", []),
        "meta_id": desc.get("meta_id", ""),
        "replace_path": [p.strip("/") for p in desc.get("replace_path", [])],
        "description": desc.get("short_description", ""),
        "multiplayer_synchronized": desc.get("multiplayer_synchronized"),
        "error": desc.get("error", ""),
        "source": source,
        "remote_id": remote_id,
        "root": str(root) if root else "",
        "exists": bool(root and _exists(root)),
    }


def list_files(root, only=()):
    """Regular files of a mod as {posix relative path: absolute path string}. Symlinks are never followed, so a
    mod cannot make the scanner read outside its own folder or loop forever. `only` limits the walk to
    those top-level folders (used for the base game). Uses os.scandir: no per-file stat calls, which is
    what made big mod lists slow on Windows."""
    out = {}
    root = str(root)

    def walk(path, rel, top):
        try:
            it = list(os.scandir(path))
        except OSError:
            return
        for e in it:
            try:
                if e.is_symlink():
                    continue
                name = e.name
                if e.is_dir(follow_symlinks=False):
                    if top and (name in SKIP_TOP or (only and name not in only)):
                        continue
                    walk(e.path, rel + name + "/", False)
                elif e.is_file(follow_symlinks=False):
                    if top and (only or name.lower() in SKIP_ROOT_FILES):
                        continue  # files directly in the root are not base content / are metadata
                    out[rel + name] = e.path
            except OSError:
                continue

    walk(root, "", True)
    return out


_TOKEN = re.compile(r'#[^\n]*|("[^"]*"|[{}]|[^\s{}="#]+|=)')


_STRUCT = re.compile(r'[{}]|"[^"]*"|#[^\n]*')


def top_level_keys(text):
    """Names defined at brace depth 0 as (key, mode). mode is None for a plain definition
    or the patch prefix ('REPLACE', 'INJECT', ...) for `PREFIX:key = {`.
    Only the braces, strings and comments are walked (a few per definition); the words between top-level blocks are
    tokenised only where a block starts. Same answers as reading every word (tests compare the two)."""
    keys, depth, start = [], 0, 0
    for m in _STRUCT.finditer(text):
        t = m.group()
        if t == "{":
            if depth == 0:
                toks = [x for x in _TOKEN.findall(text, start, m.start()) if x]
                if len(toks) >= 2 and toks[-1] == "=" and toks[-2] not in ("{", "}"):
                    k = toks[-2].strip('"')
                    mm = PATCH_PREFIX.match(k)
                    keys.append((mm.group(2), mm.group(1)) if mm else (k, None))
            depth += 1
        elif t == "}" and depth:
            depth -= 1
            if depth == 0:
                start = m.end()
    return keys


def loc_keys(text):
    """Localization keys as (lang, key) from a .yml file."""
    lang, out = None, []
    for line in text.splitlines():
        m = LOC_LANG.match(line)
        if m:
            lang = m.group(1)
            continue
        m = LOC_LINE.match(line)
        if m and lang:
            out.append((lang, m.group(1)))
    return out


WORKERS = 12   # file reads in flight at once: on Windows most of the time is waiting for the disk and the antivirus


def _adaptive_map(fn, items, per_item_slow, trial=8):
    """Like _pmap, but threads only pay off when each call mostly waits (a disk with antivirus, a network drive): the first
    `trial` calls run in line and are timed; when they average more than `per_item_slow` seconds the rest runs on threads.
    On a fast local disk threads would only fight over the interpreter lock, so they are not used there."""
    import time as _t
    items = list(items)
    t0 = _t.perf_counter()
    head = [fn(x) for x in items[:trial]]
    if len(items) <= trial:
        return head
    slow = (_t.perf_counter() - t0) / max(1, len(head)) > per_item_slow
    return head + (list(_pmap(fn, items[trial:])) if slow else [fn(x) for x in items[trial:]])


def _pmap(fn, items, window=256):
    """fn over items, results in order, with up to `window` calls running on threads at once (the waiting overlaps).
    Small jobs run inline."""
    items = list(items)
    if len(items) < 16:
        yield from map(fn, items)
        return
    from collections import deque
    from concurrent.futures import ThreadPoolExecutor
    from itertools import islice
    with ThreadPoolExecutor(WORKERS) as ex:
        it = iter(items)
        pend = deque(ex.submit(fn, x) for x in islice(it, window))
        for x in it:
            r = pend.popleft().result()
            pend.append(ex.submit(fn, x))
            yield r
        while pend:
            yield pend.popleft().result()


class ScanCancelled(Exception):
    """A newer request made the running conflict scan pointless."""


_parse_cache = {}   # (path, parser name) -> (mtime_ns, size, frozenset of keys)
_loaded = set()     # cache files already read into _parse_cache
_new_entries = 0    # parses done since the cache was last loaded or saved
_fresh = set()      # keys parsed (new or changed) in this process: what a start-up worker hands back to the app
CACHE_FORMAT = 1
MAX_CACHE = 300_000


def _cached(path, fn, trusted=None):
    """Memoize a per-file parse (as a frozenset, each key once) on (path, mtime, size) so re-analysis stays fast on
    big mod lists. `path` is a string from list_files. A path in `trusted` was checked since the mods were last read
    from disk, so it is not stat-ed again (that is one system call per file, which dominates on Windows)."""
    global _new_entries
    key = (path, fn.__name__)
    hit = _parse_cache.get(key)
    if hit is not None and trusted is not None and key in trusted:
        return hit[2]
    st = os.stat(path)
    if hit is None or hit[0] != st.st_mtime_ns or hit[1] != st.st_size:
        if len(_parse_cache) > MAX_CACHE:
            _parse_cache.clear()
        hit = _parse_cache[key] = (st.st_mtime_ns, st.st_size, frozenset(fn(_read(path))))
        _new_entries += 1
        _fresh.add(key)
    if trusted is not None:
        trusted.add(key)
    return hit[2]


def cache_dirty():
    return _new_entries > 0


def fresh_entries():
    """The parses this process made (files new or changed since the cache was saved), as {key: entry}."""
    return {k: _parse_cache[k] for k in _fresh if k in _parse_cache}


def add_entries(entries):
    """Take parses made by another process (a start-up worker); they are saved with the next save_cache."""
    global _new_entries
    if len(_parse_cache) + len(entries) > MAX_CACHE:
        _parse_cache.clear()
    _parse_cache.update(entries)
    _new_entries += len(entries)


def save_cache(path):
    """Write what was parsed to a gzip'd JSON file, so the next start does not read every mod file again."""
    global _new_entries
    import gzip
    pending = _new_entries
    rows = [[p, name, v[0], v[1], list(v[2])] for (p, name), v in list(_parse_cache.items())]
    tmp = Path(str(path) + ".tmp")
    with gzip.open(tmp, "wt", encoding="utf-8", compresslevel=3) as f:
        json.dump({"format": CACHE_FORMAT, "entries": rows}, f, separators=(",", ":"))
    os.replace(tmp, path)
    _new_entries = max(0, _new_entries - pending)


def load_cache(path):
    """Read a file made by save_cache (once per file). Anything wrong with it just means a cold start."""
    import gzip
    if str(path) in _loaded:
        return 0
    _loaded.add(str(path))
    n = 0
    try:
        with gzip.open(path, "rt", encoding="utf-8") as f:
            doc = json.load(f)
        if not isinstance(doc, dict) or doc.get("format") != CACHE_FORMAT:
            return 0
        for p, name, mtime, size, keys in doc["entries"]:
            key = (p, name)
            if name in ("top_level_keys", "loc_keys") and key not in _parse_cache:
                _parse_cache[key] = (mtime, size, frozenset(tuple(k) for k in keys))
                n += 1
    except (OSError, ValueError, KeyError, TypeError, EOFError):
        pass
    return n


def _probe_many(items):
    """For a handful of (path, parser) pairs: True where the saved parse is still right, (mtime_ns, size, text) where the file
    has to be read (new or changed), None where it cannot be read. Runs on a worker thread: stat and read are where the
    waiting is. (Bytes are decoded here, not through Path.read_text: the key finders do not care about line endings.)"""
    out = []
    for path, fn in items:
        try:
            st = os.stat(path)
            hit = _parse_cache.get((path, fn.__name__))
            if hit is not None and hit[0] == st.st_mtime_ns and hit[1] == st.st_size:
                out.append(True)
                continue
            with open(path, "rb") as f:
                out.append((st.st_mtime_ns, st.st_size, f.read().decode("utf-8-sig", errors="replace")))
        except OSError:
            out.append(None)
    return out


def prefetch(todo, trusted=None, progress=None, should_stop=None):
    """Bring the parse cache up to date for these (path, parser) pairs, reading in parallel. Files already checked since
    the mods were last read from disk (`trusted`) are skipped."""
    global _new_entries
    if trusted is not None:
        todo = [(p, fn) for p, fn in todo if (p, fn.__name__) not in trusted]
    total, done = len(todo), 0
    for i in range(0, total, 1000):   # read a batch on the threads while this thread only waits, then parse it (no fighting over the GIL)
        batch = todo[i:i + 1000]
        parts = _adaptive_map(_probe_many, [batch[j:j + 20] for j in range(0, len(batch), 20)], 0.003)   # 20 files take over 3 ms: waiting dominates
        results = [r for part in parts for r in part]
        for (path, fn), r in zip(batch, results):
            key = (path, fn.__name__)
            if r is True:
                if trusted is not None:
                    trusted.add(key)
            elif r:
                if len(_parse_cache) > MAX_CACHE:
                    _parse_cache.clear()
                _parse_cache[key] = (r[0], r[1], frozenset(fn(r[2])))
                _new_entries += 1
                _fresh.add(key)
                if trusted is not None:
                    trusted.add(key)
        done += len(batch)
        if should_stop is not None and should_stop():
            raise ScanCancelled()
        if progress:
            progress(f"reading files {done} of {total}")


def def_category(rel, def_dirs):
    """'common/traits/x.txt' -> 'common/traits'; 'in_game/common/goods/a.txt' -> 'in_game/common/goods';
    None when the file is not a script folder. Keys only clash within the same category."""
    parts = rel.split("/")
    for i, p in enumerate(parts[:-1]):
        if i > 1:
            break
        if p in def_dirs:
            return "/".join(parts[:i + 2]) if i + 2 < len(parts) else "/".join(parts[:i + 1])
    return None


def summarize(conflicts):
    """What the page is sent for one playset: the conflicts (capped), how many of each kind, and whether it was cut."""
    counts = {}
    for c in conflicts:
        k = "vanilla" if c.get("vanilla") else c["kind"]
        counts[k] = counts.get(k, 0) + 1
    cap = MAX_PER_KIND * 4
    return {"conflicts": conflicts[:cap], "counts": counts, "truncated": len(conflicts) > cap, "pending": False}


def find_conflicts(mods, order, files_cache=None, def_dirs=DEFAULT_DEF_DIRS, vanilla=None, trusted=None, should_stop=None,
                   progress=None):
    """order: list of mod ids, first loads first (later wins). `vanilla` = (game folder, only-dirs)
    treats the base game as the first mod; results involving it carry `vanilla: True`.
    `trusted` (a set) remembers which files were already checked for changes; `should_stop()` returning True between
    two mods abandons the scan with ScanCancelled. `progress(text)` is told how far the listing and reading are. File lists
    and file reads run in parallel threads before the (sequential) comparison.

    Returns list of {kind, severity, path, mods:[ids in load order], winner}; definition conflicts also carry
    `files` {mod id: [file that defines the key]} so the UI can show which file each mod overrides it in.
      file         identical relative path in several mods (whole file is overridden)
      definition   same key defined in different files of different mods
      patch        INJECT:/TRY_INJECT: onto a key (info: these merge rather than override)
      replace      a mod's replace_path wipes files that earlier mods provide
      localization same loc key in different files (info; never reported against the base game)
    REPLACE: definitions are intentional overrides (info) unless the winner is a plain redefinition.
    """
    cache = files_cache if files_cache is not None else {}
    parse = _cached if trusted is None else (lambda p, fn: _cached(p, fn, trusted))
    mods = dict(mods)
    order = list(order)
    if vanilla:
        mods[VANILLA] = {"exists": True, "root": str(vanilla[0]), "replace_path": [], "only": tuple(vanilla[1] or ())}
        order = [VANILLA] + order
    seen_files, seen_defs, seen_patch, seen_loc = defaultdict(list), {}, defaultdict(list), defaultdict(list)
    replaced = []
    loaded = []  # (mid, files)
    van_files = {}
    dir_cat = {}  # script category per directory (it only depends on the folders of the path)

    def category(rel):
        d = rel.rpartition("/")[0]
        if d not in dir_cat:
            dir_cat[d] = def_category(rel, def_dirs)
        return dir_cat[d]

    def parser_for(rel):
        if rel.endswith(".txt") and category(rel):
            return top_level_keys
        if rel.endswith(".yml") and "localization" in rel.split("/")[:2] and "/replace/" not in rel:
            return loc_keys
        return None

    # ahead of the comparison, in parallel: every mod's file list, then every file that has to be read
    roots = []
    for mid in order:
        m = mods.get(mid)
        if m and m["exists"]:
            k = (m["root"], tuple(m.get("only", ())))
            if k not in cache and k not in roots:
                roots.append(k)
    for i in range(0, len(roots), 200):
        part = roots[i:i + 200]
        for k, listing in zip(part, _adaptive_map(lambda k: list_files(k[0], k[1]), part, 0.004)):
            cache[k] = listing
        if should_stop is not None and should_stop():
            raise ScanCancelled()
        if progress:
            progress(f"listing files {min(i + 200, len(roots))} of {len(roots)} mods")
    todo = []
    for mid in order:
        m = mods.get(mid)
        if m and m["exists"] and mid != VANILLA:
            todo += [(p, fn) for rel, p in cache[(m["root"], tuple(m.get("only", ())))].items() if (fn := parser_for(rel))]
    prefetch(todo, trusted, progress, should_stop)
    if progress:
        progress(f"comparing {len(order)} mods")

    for mid in order:
        if should_stop is not None and should_stop():
            raise ScanCancelled()
        m = mods.get(mid)
        if not m or not m["exists"]:
            continue
        key = (m["root"], tuple(m.get("only", ())))
        if key not in cache:
            cache[key] = list_files(m["root"], m.get("only", ()))
        files = cache[key]
        for rp in m["replace_path"]:
            n, hit = 0, []
            for pm, pfiles in loaded:
                c = sum(1 for r in pfiles if r.startswith(rp + "/"))
                if c:
                    n += c
                    hit.append(pm)
            if hit:
                replaced.append({"kind": "replace", "severity": "warn", "path": f"{rp}/ ({n} files)",
                                 "mods": hit + [mid], "winner": mid})
        loaded.append((mid, files))
        if mid == VANILLA:  # parsed lazily below, only where a mod defines the same keys
            van_files = files
            for rel in files:
                seen_files[rel].append(mid)
            continue
        for rel, p in files.items():
            seen_files[rel].append(mid)
            cat = category(rel) if rel.endswith(".txt") else None
            if cat:
                for k, mode in parse(p, top_level_keys):
                    if mode and "INJECT" in mode:
                        seen_patch[(cat, k)].append(mid)
                    else:   # nearly every key is defined once: keep that as a bare tuple, a list only once a second one shows up
                        kk = (cat, k)
                        prev = seen_defs.get(kk)
                        if prev is None:
                            seen_defs[kk] = (mid, rel, mode)
                        elif type(prev) is tuple:
                            seen_defs[kk] = [prev, (mid, rel, mode)]
                        else:
                            prev.append((mid, rel, mode))
            elif "localization" in rel.split("/")[:2] and rel.endswith(".yml") and "/replace/" not in rel:
                for lang, k in parse(p, loc_keys):
                    seen_loc[(lang, k)].append((mid, rel))
    if van_files:
        wanted = {c for c, _ in seen_defs}
        prefetch([(p, top_level_keys) for rel, p in van_files.items() if rel.endswith(".txt") and category(rel) in wanted],
                 trusted, progress, should_stop)
        for rel, p in van_files.items():
            cat = category(rel) if rel.endswith(".txt") else None
            if cat in wanted:
                for k, mode in parse(p, top_level_keys):
                    if not (mode and "INJECT" in mode) and (cat, k) in seen_defs:
                        prev = seen_defs[(cat, k)]
                        seen_defs[(cat, k)] = [prev, (VANILLA, rel, mode)] if type(prev) is tuple else prev + [(VANILLA, rel, mode)]
    out = []
    for rel, ids in sorted(seen_files.items()):
        if len(ids) > 1:
            out.append({"kind": "file", "severity": "warn", "path": rel, "mods": ids, "winner": ids[-1]})
    for (cat, k), entries in sorted(seen_defs.items()):
        if type(entries) is tuple:  # nearly every key: one mod defines it, nothing to compare
            continue
        ids = {i for i, _, _ in entries}
        by_file = {}  # which mods define the key in which file (only built for the few keys that are shared)
        for i, rel, md in entries:
            by_file.setdefault(rel, []).append((i, md))
        if len(ids) > 1 and len(by_file) > 1:  # same-file clashes are already 'file' conflicts
            ordered = [i for i in order if i in ids]
            winner = ordered[-1]
            intentional = any(md and md.startswith("REPLACE") for i, _, md in entries if i == winner)
            files = {}
            for rel, es in by_file.items():
                for i, _ in es:
                    files.setdefault(i, []).append(rel)
            out.append({"kind": "definition", "severity": "info" if intentional else "warn",
                        "path": f"{cat}: {k}", "mods": ordered, "winner": winner, "files": files})
    for (cat, k), ids in sorted(seen_patch.items()):
        ordered = [i for i in order if i in set(ids)]
        out.append({"kind": "patch", "severity": "info", "path": f"{cat}: {k}", "mods": ordered,
                    "winner": ordered[-1]})
    for (lang, k), entries in sorted(seen_loc.items()):
        if len(entries) < 2:
            continue
        ids = {i for i, _ in entries}
        rels = {r for _, r in entries}
        if len(ids) > 1 and len(rels) > 1 and len(rels) == len(entries):  # every file counted once
            ordered = [i for i in order if i in ids]
            out.append({"kind": "localization", "severity": "info", "path": f"{lang}: {k}",
                        "mods": ordered, "winner": ordered[-1]})
    out.extend(replaced)
    for x in out:
        if x["mods"][0] == VANILLA and len(x["mods"]) == 2:  # one mod vs the base game; 2+ mods is a real clash
            x["vanilla"] = True
    return out
