"""Side-by-side comparison of two playsets."""
import bisect

SETTINGS = ("auto_sort", "separate_saves", "launch_args", "notes")


def _enabled(ps):
    off = set(ps["disabled"])
    return [m for m in ps["mods"] if m not in off]


def _lis(seq):
    """Indices of one longest increasing subsequence of `seq` (patience sorting, O(n log n))."""
    tails, tail_idx, prev = [], [], [-1] * len(seq)
    for i, v in enumerate(seq):
        k = bisect.bisect_left(tails, v)
        if k == len(tails):
            tails.append(v)
            tail_idx.append(i)
        else:
            tails[k], tail_idx[k] = v, i
        prev[i] = tail_idx[k - 1] if k else -1
    out, i = [], tail_idx[-1] if tail_idx else -1
    while i != -1:
        out.append(i)
        i = prev[i]
    return out[::-1]


def compare_playsets(mods, a, b):
    """Compare playset dicts `a` and `b`. Mod ids are returned; the caller resolves names.

    only_a / only_b   enabled in one playset and not present at all in the other
    state             present in both but enabled in only one: {id, a: 'enabled'|'disabled', b: ...}
    moved             enabled in both, but in a different relative position. Reported minimally: the largest
                      set of mods that keep their relative order is treated as unchanged, the rest are 'moved'
    """
    ea, eb = _enabled(a), _enabled(b)
    sa, sb, la, lb = set(ea), set(eb), set(a["mods"]), set(b["mods"])
    only_a = [m for m in ea if m not in lb]
    only_b = [m for m in eb if m not in la]
    state = ([{"id": m, "a": "enabled", "b": "disabled"} for m in ea if m in lb and m not in sb] +
             [{"id": m, "a": "disabled", "b": "enabled"} for m in eb if m in la and m not in sa])
    common = [m for m in ea if m in sb]
    pos_b = {m: i for i, m in enumerate(m for m in eb if m in sa)}
    seq = [pos_b[m] for m in common]
    keep = set(_lis(seq))
    pos_a_abs = {m: i + 1 for i, m in enumerate(ea)}
    pos_b_abs = {m: i + 1 for i, m in enumerate(eb)}
    moved = [{"id": m, "a": pos_a_abs[m], "b": pos_b_abs[m]} for i, m in enumerate(common) if i not in keep]
    same = [m for i, m in enumerate(common) if i in keep]
    settings = [{"field": f, "a": a.get(f), "b": b.get(f)} for f in SETTINGS if a.get(f) != b.get(f)]
    identical = not (only_a or only_b or state or moved or settings)
    return {"only_a": only_a, "only_b": only_b, "state": state, "moved": moved, "same": same,
            "common_order_b": [m for m in eb if m in sa], "settings": settings, "identical": identical}
