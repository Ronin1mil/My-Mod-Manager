"""Load-order engine: validates a selection of mods and sorts it so every mod loads after
the mods it depends on.

The sort is a *stable* topological sort: among mods whose constraints are satisfied, the
order the user chose wins, so a manual arrangement is preserved wherever no rule says
otherwise. Every position comes with a human readable explanation.
"""
import heapq


def version_matches(supported, game):
    """'1.7.*' / '1.7' / '1.7.6' vs an installed '1.7.6'. Empty on either side matches."""
    if not supported or not game:
        return True
    s = supported.lstrip("v").split(".")
    g = game.lstrip("v").split(".")
    for i, part in enumerate(s):
        if part == "*":
            return True
        if i >= len(g) or g[i] != part:
            return False
    return True


def name_index(mods):
    """Map every way a dependency can name a mod (display name, workshop id, ugc_<id>) to its id."""
    idx = {}
    for m in mods.values():
        idx.setdefault(m["name"], m["id"])
        if m.get("remote_id"):
            idx[str(m["remote_id"])] = m["id"]
            idx[f"ugc_{m['remote_id']}"] = m["id"]
        if m.get("meta_id"):
            idx.setdefault(m["meta_id"], m["id"])
    return idx


def resolve(idx, m, dep):
    """Id of the mod that `dep` (a name, as written in mod `m`) refers to: its metadata id first, then the name."""
    did = m.get("dependency_ids", {}).get(dep)
    return (idx.get(did) if did else None) or idx.get(dep)


def _issue(severity, code, module, msg, related=None, fix=None):
    return {"severity": severity, "code": code, "module": module, "related": related,
            "message": msg, "fix": fix}


def _dedupe(selection):
    seen = set()
    return [s for s in selection if not (s in seen or seen.add(s))]


def _name(mods, mid):
    return mods[mid]["name"] if mid in mods else mid


def missing_required(mods, selection):
    """Installed mods that the selection needs (transitively) but does not contain, dependency first.
    Iterative so a very deep dependency chain cannot exhaust the recursion limit."""
    idx, chosen, seen, out = name_index(mods), set(selection), set(), []
    for root in selection:
        stack = [(root, iter(mods.get(root, {}).get("dependencies", [])))]
        while stack:
            mid, deps = stack[-1]
            for dep in deps:
                did = resolve(idx, mods.get(mid, {}), dep)
                if did is not None and did not in seen:
                    seen.add(did)
                    stack.append((did, iter(mods.get(did, {}).get("dependencies", []))))
                    break
            else:
                stack.pop()
                if mid not in chosen:
                    out.append(mid)
    return out


def validate(mods, selection, game_version=""):
    idx, chosen = name_index(mods), set(selection)
    issues, names = [], {}
    for mid in selection:
        m = mods.get(mid)
        if not m or not m["exists"]:
            issues.append(_issue("error", "missing_module", mid,
                                 f"'{_name(mods, mid)}' is in this playset but its files were not found "
                                 "(uninstalled or moved)."))
            continue
        names.setdefault(m["name"], []).append(mid)
        if not version_matches(m["supported_version"], game_version):
            issues.append(_issue("warning", "version_mismatch", mid,
                                 f"{m['name']} was made for {m['supported_version']}, "
                                 f"but the game is {game_version}."))
        if m.get("error"):
            issues.append(_issue("warning", "metadata_error", mid, f"{m['name']}: {m['error']}."))
        for dep in m["dependencies"]:
            did = resolve(idx, m, dep)
            if did is None:
                issues.append(_issue("error", "missing_dependency", mid,
                                     f"{m['name']} needs '{dep}', which is not installed.", dep))
            elif did not in chosen:
                issues.append(_issue("error", "disabled_dependency", mid,
                                     f"{m['name']} needs {_name(mods, did)}, which is not enabled in this playset.",
                                     did, {"kind": "enable", "id": did}))
        for inc in m.get("incompatible", []):
            iid = resolve(idx, m, inc)
            if iid in chosen and iid != mid and mid < iid:
                issues.append(_issue("error", "incompatible", mid,
                                     f"{m['name']} is incompatible with {_name(mods, iid)} - disable one of them.",
                                     iid))
    for name, ids in names.items():
        if len(ids) > 1:
            for mid in ids:
                issues.append(_issue("warning", "duplicate", mid, f"Another enabled mod is also called '{name}'.",
                                     next(i for i in ids if i != mid)))
    return issues


def _edges(mods, nodes):
    idx, present, seen, edges = name_index(mods), set(nodes), set(), []
    for mid in nodes:
        for dep in mods[mid]["dependencies"]:
            did = resolve(idx, mods[mid], dep)
            if did and did != mid and did in present and (did, mid) not in seen:
                seen.add((did, mid))
                edges.append((did, mid))
        # soft rules (Bannerlord modules): only when the other mod is present, never a warning when it is not
        for dep in mods[mid].get("load_after", []):
            did = resolve(idx, mods[mid], dep)
            if did and did != mid and did in present and (did, mid) not in seen:
                seen.add((did, mid))
                edges.append((did, mid))
        for oth in mods[mid].get("load_before", []):
            oid = resolve(idx, mods[mid], oth)
            if oid and oid != mid and oid in present and (mid, oid) not in seen:
                seen.add((mid, oid))
                edges.append((mid, oid))
    return edges


def compute_order(mods, selection, auto=True, game_version=""):
    """Validate `selection` (enabled mod ids in the user's order) and compute the load order.

    auto=True  -> returned order satisfies every rule (when no cycle exists)
    auto=False -> the user's order is kept; rule violations become issues with an auto-sort fix
    Returns {order, notes: {id: {moved, reason}}, issues}.
    """
    selection = _dedupe(selection)
    issues = validate(mods, selection, game_version)
    nodes = [s for s in selection if s in mods]
    user_pos = {s: i for i, s in enumerate(nodes)}
    edges = _edges(mods, nodes)
    incoming = {}
    for a, b in edges:
        incoming.setdefault(b, []).append(a)

    indeg = {n: 0 for n in nodes}
    out_edges = {}
    for a, b in edges:
        indeg[b] += 1
        out_edges.setdefault(a, []).append(b)
    rank = lambda n: mods[n].get("rank", 0)  # official Bannerlord modules sort ahead of the rest when nothing else decides
    heap = [(rank(n), user_pos[n], n) for n in nodes if indeg[n] == 0]
    heapq.heapify(heap)
    sorted_ids = []
    while heap:
        _, _, mid = heapq.heappop(heap)
        sorted_ids.append(mid)
        for t in out_edges.get(mid, []):
            indeg[t] -= 1
            if indeg[t] == 0:
                heapq.heappush(heap, (rank(t), user_pos[t], t))
    if len(sorted_ids) < len(nodes):  # whatever never reached in-degree 0 sits on or behind a loop
        done = set(sorted_ids)
        stuck = [n for n in nodes if n not in done]
        issues.append(_issue("error", "cycle", stuck[0],
                             "These mods require each other in a loop, so no valid order exists: "
                             + ", ".join(_name(mods, s) for s in stuck) + ".",
                             stuck[1] if len(stuck) > 1 else None))
        sorted_ids.extend(stuck)
    order = sorted_ids if auto else list(nodes)

    pos = {s: i for i, s in enumerate(order)}
    if not auto:
        for a, b in edges:
            if pos[a] > pos[b]:
                issues.append(_issue("error", "wrong_order", b,
                                     f"{_name(mods, b)} must load after {_name(mods, a)} (dependency).",
                                     a, {"kind": "autosort"}))
    notes = {}
    for mid in order:
        deps = sorted(_name(mods, a) for a in incoming.get(mid, []))
        reason = (f"Loads after {', '.join(deps)} (dependency)." if deps
                  else "Official module: loads before the others." if mods.get(mid, {}).get("official")
                  else "Keeps the position you gave it.")
        notes[mid] = {"moved": auto and user_pos.get(mid) != pos[mid], "reason": reason}
    issues.sort(key=lambda i: 0 if i["severity"] == "error" else 1)
    return {"order": order, "notes": notes, "issues": issues}


def sort_playset(mods, playset_mods, disabled, game_version=""):
    """Sort only the enabled mods; disabled ones keep their slots. Returns the new full list."""
    playset_mods, off = _dedupe(playset_mods), set(disabled)
    enabled = [m for m in playset_mods if m not in off]
    res = compute_order(mods, enabled, True, game_version)["order"]
    res += [m for m in enabled if m not in mods]  # uninstalled ids ride along at the end
    it = iter(res)
    return [m if m in off else next(it) for m in playset_mods]
