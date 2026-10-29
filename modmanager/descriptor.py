"""Parsers for Paradox .mod descriptors (Clausewitz subset) and the newer metadata.json."""
import json
import re

_TOKEN = re.compile(r'#[^\n]*|"((?:[^"\\]|\\.)*)"|([{}=])|([^\s{}="#]+)')
# where a mod keeps metadata.json (first hit wins)
META_PATHS = (".metadata/metadata.json", "metadata/metadata.json", "metadata.json")
LIST_KEYS = {"tags", "dependencies", "replace_path", "supported_extensions"}


def _tokens(text):
    for m in _TOKEN.finditer(text):
        if m.group(0).startswith("#"):
            continue
        if m.group(1) is not None:
            yield ("str", m.group(1).replace('\\"', '"'))
        elif m.group(2):
            yield (m.group(2), m.group(2))
        else:
            yield ("str", m.group(3))


def parse_descriptor(text):
    """Parse a .mod file. List-like keys (tags, dependencies, replace_path) become lists."""
    toks = list(_tokens(text))
    out, i = {}, 0
    while i < len(toks):
        kind, key = toks[i]
        if kind != "str" or i + 1 >= len(toks) or toks[i + 1][0] != "=":
            i += 1
            continue
        i += 2
        if i >= len(toks):
            break
        if toks[i][0] == "{":
            i += 1
            items = []
            while i < len(toks) and toks[i][0] != "}":
                items.append(toks[i][1])
                i += 1
            i += 1
            out.setdefault(key, []).extend(items)
        else:
            val = toks[i][1]
            i += 1
            if key in LIST_KEYS:
                out.setdefault(key, []).append(val)
            else:
                out[key] = val
    for k in LIST_KEYS:
        out.setdefault(k, [])
    return out


def _str(v):
    return v if isinstance(v, str) else (str(v) if isinstance(v, (int, float)) and not isinstance(v, bool) else "")


def _strs(v):
    return [x for x in (_str(i) for i in v) if x] if isinstance(v, list) else []


def parse_metadata(text):
    """Parse metadata.json into the same shape parse_descriptor returns, plus 'dependency_ids'
    ({name: id}), 'multiplayer_synchronized' (bool|None), 'short_description' and 'meta_id'.
    Wrong-typed fields are ignored. Relationship kinds are read from 'rel_type' or 'type'."""
    try:
        d = json.loads(text.lstrip("\ufeff"))
    except ValueError:
        return {}
    if not isinstance(d, dict):
        return {}
    custom = d.get("game_custom_data")
    custom = custom if isinstance(custom, dict) else {}
    deps, incompatible, dep_ids = [], [], {}
    rels = d.get("relationships")
    for r in rels if isinstance(rels, list) else []:
        if not isinstance(r, dict):
            continue
        rid = _str(r.get("id"))
        name = _str(r.get("display_name")) or _str(r.get("name")) or rid
        kind = str(r.get("rel_type") or r.get("type") or "dependency").lower()
        if kind == "dependency" and name:
            deps.append(name)
            if rid:
                dep_ids[name] = rid
        elif kind in ("incompatible", "incompatibility") and name:
            incompatible.append(name)
            if rid:
                dep_ids[name] = rid
    mp = custom.get("multiplayer_synchronized")
    out = {
        "name": _str(d.get("name")),
        "version": _str(d.get("version")),
        "supported_version": _str(d.get("supported_game_version")) or _str(d.get("game_version")),
        "tags": _strs(d.get("tags")),
        "dependencies": deps,
        "incompatible": incompatible,
        "dependency_ids": dep_ids,
        "replace_path": _strs(custom.get("replace_paths")) or _strs(custom.get("replace_path")),
        "short_description": _str(d.get("short_description")) or _str(d.get("description")),
        "meta_id": _str(d.get("id")),
        "multiplayer_synchronized": mp if isinstance(mp, bool) else None,
    }
    return {k: v for k, v in out.items() if v not in ("", [], {}, None)}
