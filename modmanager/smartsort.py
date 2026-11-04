"""Conflict-aware sorting: on top of the dependency rules, decide the load order of mods that overwrite each other.

Nothing in the game files says which of two clashing mods should win, so these are rules of thumb the modding
community uses, applied only where two enabled mods really overlap, and never against a dependency rule:

  replace_path  a mod that wipes a folder (replace_path) loads before the mods that add files to that folder,
                otherwise it deletes them
  built on      a mod whose name contains the other mod's whole name (a patch or add-on made for it) loads after it
  patch         a mod called a compatibility patch / compatch / patch / submod loads after the mod it clashes with
  size          of two clashing mods, the one with far more files (the overhaul) loads first, so the small tweak
                is not overwritten by it

Where none of these decides (two mods of similar size, no patch wording) the order you chose stays and the pair is
listed in the report. Every rule becomes an extra "A before B" edge for order.compute_order. An edge that would
contradict a dependency rule, or a stronger rule already taken, is dropped, so the result never has a loop.
"""
import itertools
import re

from . import order as order_mod
from .scan import VANILLA

# priority of each rule (higher is applied first)
REPLACE, BUILT_ON, PATCH, SIZE = 4, 3, 2, 1
SIZE_RATIO = 1.5      # one mod needs at least this many times the files of the other for "the bigger one first"
MAX_GROUP = 12        # a file clashed by more mods than this is compared on its 12 loading last
MAX_EDGES = 2000      # rules worked on per sort (the strongest first)
PATCHY = re.compile(r"(compat|patch|submod|sub-mod|add-?on)", re.I)


def _pairs(conflicts, nodes):
    """{(a, b): number of clashes} for every pair of enabled mods that overwrite each other (file or definition clashes
    that are not marked intentional). The base game and intentional REPLACE overrides do not count."""
    count = {}
    for c in conflicts:
        if c.get("kind") not in ("file", "definition") or c.get("severity") != "warn":
            continue
        ids = [i for i in c["mods"] if i != VANILLA and i in nodes][-MAX_GROUP:]
        for a, b in itertools.combinations(sorted(ids), 2):
            count[(a, b)] = count.get((a, b), 0) + 1
    return count


def _reaches(adj, src, dst):
    seen, todo = {src}, [src]
    while todo:
        n = todo.pop()
        if n == dst:
            return True
        for t in adj.get(n, ()):
            if t not in seen:
                seen.add(t)
                todo.append(t)
    return False


def _name(mods, mid):
    return mods[mid]["name"] if mid in mods else mid


def _decide(mods, a, b, sizes):
    """For two clashing mods: (first, second, priority, why) or None when no rule decides."""
    na, nb = _name(mods, a).lower(), _name(mods, b).lower()
    for x, y, nx, ny in ((a, b, na, nb), (b, a, nb, na)):   # x built on y
        if len(ny) >= 5 and ny in nx and nx != ny:
            return y, x, BUILT_ON, f"{_name(mods, x)} is made for {_name(mods, y)} (its name contains it), so it loads after"
    pa, pb = bool(PATCHY.search(na)), bool(PATCHY.search(nb))
    if pa != pb:
        x, y = (a, b) if pa else (b, a)   # x is the patch
        return y, x, PATCH, f"{_name(mods, x)} looks like a patch (by its name), so it loads after the mod it clashes with"
    sa, sb = sizes.get(a, 0), sizes.get(b, 0)
    big, small = (a, b) if sa >= sb else (b, a)
    sbig, ssmall = max(sa, sb), min(sa, sb)
    if ssmall > 0 and sbig >= SIZE_RATIO * ssmall:
        return big, small, SIZE, (f"{_name(mods, small)} is a smaller mod ({ssmall} files against {sbig}), so it loads "
                                  f"after {_name(mods, big)} and its changes are not overwritten")
    return None


def plan(mods, nodes, conflicts, sizes):
    """nodes: the enabled mod ids. conflicts: scan.find_conflicts output for them (all of it, not the capped page list).
    sizes: {mod id: number of files}. -> {"edges": [(first, second, why)], "report": {...}}"""
    nodeset = set(nodes)
    adj = {}
    for a, b in order_mod._edges(mods, [n for n in nodes if n in mods]):
        adj.setdefault(a, set()).add(b)
    cands = []   # (priority, weight, first, second, why)
    for c in conflicts:   # a mod that wipes a folder goes before the mods that add files there
        if c.get("kind") == "replace" and len(c["mods"]) > 1 and c["winner"] in nodeset:
            r = c["winner"]
            for h in c["mods"]:
                if h != r and h in nodeset:
                    cands.append((REPLACE, 1000, r, h, f"{_name(mods, r)} replaces a folder that {_name(mods, h)} adds "
                                                       f"files to, so it loads first and {_name(mods, h)} keeps them"))
    pairs = _pairs(conflicts, nodeset)
    ties = []
    for (a, b), n in pairs.items():
        d = _decide(mods, a, b, sizes)
        if d is None:
            ties.append({"a": a, "b": b, "clashes": n})
        else:
            cands.append((d[2], n, d[0], d[1], d[3]))
    cands.sort(key=lambda t: (-t[0], -t[1]))
    taken, dropped, seen = [], 0, set()
    for pr, n, x, y, why in cands[:MAX_EDGES]:
        if (x, y) in seen or y in adj.get(x, ()):
            continue
        if _reaches(adj, y, x):   # would contradict a dependency rule or something stronger already taken
            dropped += 1
            continue
        adj.setdefault(x, set()).add(y)
        seen.add((x, y))
        taken.append((x, y, why, n, pr))
    ties.sort(key=lambda t: -t["clashes"])
    report = {"rules": [{"first": x, "second": y, "why": why, "clashes": n} for x, y, why, n, _ in taken],
              "ties": ties[:30], "tie_count": len(ties), "dropped": dropped + max(0, len(cands) - MAX_EDGES)}
    return {"edges": [(x, y, why) for x, y, why, _, _ in taken], "report": report}
