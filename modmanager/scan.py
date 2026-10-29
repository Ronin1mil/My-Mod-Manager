"""Discover installed mods and analyse files/definitions/localization for conflicts."""
import json
import os
import re
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


def _read(p):
    return Path(p).read_text(encoding="utf-8-sig", errors="replace")


def _meta_file(root):
    for rel in META_PATHS:
        f = Path(root) / rel
        if f.is_file():
            return f
    return None


def looks_like_mod(d):
    return _meta_file(d) is not None or (Path(d) / "descriptor.mod").is_file()


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
    """Return {mod_id: info}. mod_id is 'ws:<id>' or 'local:<name>'."""
    mods = {}
    if workshop_dir and Path(workshop_dir).is_dir():
        for d in sorted(Path(workshop_dir).iterdir()):
            if d.is_dir() and looks_like_mod(d):
                df = d / "descriptor.mod"
                desc = _load_desc(df if df.is_file() else None, d)
                mods[f"ws:{d.name}"] = _info(f"ws:{d.name}", desc, d, "workshop", d.name)
    if user_dir and (Path(user_dir) / "mod").is_dir():
        mod_dir = Path(user_dir) / "mod"
        for f in sorted(mod_dir.glob("*.mod")):
            desc = parse_descriptor(_read(f))
            rid = desc.get("remote_file_id")
            root = _mod_root(f, desc)
            mid = f"ws:{rid}" if rid and f"ws:{rid}" in mods else f"local:{f.stem}"
            if mid in mods:  # descriptor stub for a workshop mod we already found
                continue
            mods[mid] = _info(mid, _load_desc(f, root), root, "local", rid)
        for d in sorted(mod_dir.iterdir()):  # bare folders with their own metadata
            if d.is_dir() and looks_like_mod(d) and not any(m["root"] == str(d) for m in mods.values()):
                df = d / "descriptor.mod"
                mid = f"local:{d.name}"
                mods.setdefault(mid, _info(mid, _load_desc(df if df.is_file() else None, d), d, "local", None))
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
        "exists": bool(root and Path(root).exists()),
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


def top_level_keys(text):
    """Names defined at brace depth 0 as (key, mode). mode is None for a plain definition
    or the patch prefix ('REPLACE', 'INJECT', ...) for `PREFIX:key = {`."""
    keys, depth = [], 0
    tok = re.compile(r'#[^\n]*|("[^"]*"|[{}]|[^\s{}="#]+|=)')
    toks = [m.group(1) for m in tok.finditer(text) if m.group(1)]
    for j, t in enumerate(toks):
        if t == "{":
            depth += 1
        elif t == "}":
            depth = max(0, depth - 1)
        elif depth == 0 and j + 2 < len(toks) and toks[j + 1] == "=" and toks[j + 2] == "{":
            k = t.strip('"')
            m = PATCH_PREFIX.match(k)
            keys.append((m.group(2), m.group(1)) if m else (k, None))
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


_parse_cache = {}


def _cached(path, fn):
    """Memoize a per-file parse on (path, mtime, size) so re-analysis stays fast on big mod lists."""
    st = Path(path).stat()
    key = (str(path), st.st_mtime_ns, st.st_size, fn.__name__)
    hit = _parse_cache.get(key)
    if hit is None:
        if len(_parse_cache) > 300_000:
            _parse_cache.clear()
        hit = _parse_cache[key] = fn(_read(path))
    return hit


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


def find_conflicts(mods, order, files_cache=None, def_dirs=DEFAULT_DEF_DIRS, vanilla=None):
    """order: list of mod ids, first loads first (later wins). `vanilla` = (game folder, only-dirs)
    treats the base game as the first mod; results involving it carry `vanilla: True`.

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
    mods = dict(mods)
    order = list(order)
    if vanilla:
        mods[VANILLA] = {"exists": True, "root": str(vanilla[0]), "replace_path": [], "only": tuple(vanilla[1] or ())}
        order = [VANILLA] + order
    seen_files, seen_defs, seen_patch, seen_loc, replaced = {}, {}, {}, {}, []
    loaded = []  # (mid, files)
    van_files = {}
    for mid in order:
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
        for rel, p in files.items():
            seen_files.setdefault(rel, []).append(mid)
            if mid == VANILLA:  # parsed lazily below, only where a mod defines the same keys
                van_files = files
                continue
            cat = def_category(rel, def_dirs) if rel.endswith(".txt") else None
            if cat:
                for k, mode in set(_cached(p, top_level_keys)):
                    if mode and "INJECT" in mode:
                        seen_patch.setdefault((cat, k), []).append(mid)
                    else:
                        seen_defs.setdefault((cat, k), {}).setdefault(rel, []).append((mid, mode))
            elif mid != VANILLA and "localization" in rel.split("/")[:2] and rel.endswith(".yml") \
                    and "/replace/" not in rel:
                for lang, k in set(_cached(p, loc_keys)):
                    seen_loc.setdefault((lang, k), {}).setdefault(rel, []).append(mid)
    if van_files:
        wanted = {c for c, _ in seen_defs}
        for rel, p in van_files.items():
            cat = def_category(rel, def_dirs) if rel.endswith(".txt") else None
            if cat in wanted:
                for k, mode in set(_cached(p, top_level_keys)):
                    if not (mode and "INJECT" in mode) and (cat, k) in seen_defs:
                        seen_defs[(cat, k)].setdefault(rel, []).append((VANILLA, mode))
    out = []
    for rel, ids in sorted(seen_files.items()):
        if len(ids) > 1:
            out.append({"kind": "file", "severity": "warn", "path": rel, "mods": ids, "winner": ids[-1]})
    for (cat, k), by_file in sorted(seen_defs.items()):
        entries = [e for v in by_file.values() for e in v]
        ids = {i for i, _ in entries}
        if len(ids) > 1 and len(by_file) > 1:  # same-file clashes are already 'file' conflicts
            ordered = [i for i in order if i in ids]
            winner = ordered[-1]
            intentional = any(md and md.startswith("REPLACE") for i, md in entries if i == winner)
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
    for (lang, k), by_file in sorted(seen_loc.items()):
        ids = {i for v in by_file.values() for i in v}
        if len(ids) > 1 and len(by_file) > 1 and not any(len(v) > 1 for v in by_file.values()):
            ordered = [i for i in order if i in ids]
            out.append({"kind": "localization", "severity": "info", "path": f"{lang}: {k}",
                        "mods": ordered, "winner": ordered[-1]})
    out.extend(replaced)
    for x in out:
        if x["mods"][0] == VANILLA and len(x["mods"]) == 2:  # one mod vs the base game; 2+ mods is a real clash
            x["vanilla"] = True
    return out
