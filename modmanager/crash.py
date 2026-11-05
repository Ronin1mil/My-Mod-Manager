"""Crash help (beta): read what the game wrote to its own logs and point at the likely cause.

Nothing here can know for certain which mod broke the game. It collects evidence and ranks it:

  * the game's logs and its newest crash folder are read (the last part of each file);
  * every error / warning line is matched to the mods it names (by the mod folder or Workshop id in a path, or
    by the mod's name);
  * known crash signatures (out of memory, access violation, graphics driver, a missing assembly ...) are named;
  * the app's own findings count too: missing or disabled dependencies, incompatible mods, mods built for another
    game version, and mods added or updated since the app last looked.

Read-only. Mod names, ids and log lines stay on this PC; the Windows user name is replaced by <user>.
Where each game keeps its logs is partly UNVERIFIED (docs/23-crash-help.md): the file list is shown in the result.
"""
import os
import re
import time
from pathlib import Path

from . import gamelog

TEXT_EXT = {".log", ".txt", ".yml", ".yaml", ".json", ".xml", ".html", ".htm"}
SKIP_NAMES = ("module_list", "dxdiag", "installed", "mod_list", "launcher")   # lists of everything loaded: no evidence
MAX_TAIL = 3 * 1024 * 1024      # read at most the last 3 MB of a file
MAX_FILES = 12
MAX_LINES = 40000
MAX_SUSPECTS = 15

ERR = re.compile(r"\b(error|exception|fatal|crash(?:ed)?|unhandled|assert(?:ion)?|failed|failure|cannot|can't)\b", re.I)
WARN = re.compile(r"\b(warn(?:ing)?|missing|not found|invalid|unexpected|unknown|could not|couldn't|deprecated)\b", re.I)
PATH_RE = re.compile(r"(?:^|[\\/\"'\s=(\[])(?:mod|mods|Modules|content[\\/]\d{5,8})[\\/]([^\\/\s\"'<>|:*?]+)", re.I)
UGC_RE = re.compile(r"ugc_(\d{6,12})", re.I)
ID_RE = re.compile(r"(?<!\d)(\d{8,10})(?!\d)")

# (pattern, kind, title, advice)
SIGNATURES = [
    (re.compile(r"out of memory|bad_alloc|OutOfMemory|not enough (?:memory|storage)", re.I), "memory", "The game ran out of memory",
     "Too many or too large mods for the memory you have. Disable the biggest texture / overhaul mods, close other programs, and make sure Windows has a page file."),
    (re.compile(r"EXCEPTION_STACK_OVERFLOW|stack overflow", re.I), "stack", "A stack overflow (something calls itself forever)",
     "Often two mods that fight over the same script, or an event / on_action loop. Check the suspects and the Conflicts tab."),
    (re.compile(r"EXCEPTION_ACCESS_VIOLATION|access violation|0xC0000005", re.I), "access", "The game crashed inside its own code (access violation)",
     "Usually a mod with broken data, or a mod made for another game version. Update the suspects, or disable them one by one."),
    (re.compile(r"DXGI_ERROR|device (?:was )?removed|device hung|VK_ERROR_DEVICE_LOST|d3d1[12].*(?:fail|error)", re.I), "gpu", "The graphics driver stopped",
     "Update the graphics driver, lower graphics settings, and disable texture / graphics mods."),
    (re.compile(r"Could not load file or assembly '([^',]+)", re.I), "assembly", "A module needs a file that is missing",
     "Install the module that provides it (often Harmony, ButterLib or UIExtenderEx) and make sure it loads before the module that needs it."),
    (re.compile(r"TypeLoadException|MissingMethodException|MissingFieldException|MissingMemberException", re.I), "version", "A module was built for a different game version",
     "Update that module, or the game, so they match."),
    (re.compile(r"NullReferenceException|InvalidOperationException|KeyNotFoundException|ArgumentException", re.I), "dotnet", "A .NET error inside a module",
     "The first module named in the stack trace is the usual culprit. See the suspects."),
    (re.compile(r"unhandled exception|fatal error", re.I), "unhandled", "An unhandled error ended the game",
     "See the suspects and the lines below for what it was doing."),
]


def log_files(game, user_dir, programdata=None):
    """The log and crash files worth reading: [{path, label, mtime, size}], newest first."""
    programdata = programdata if programdata is not None else os.environ.get("PROGRAMDATA", "")
    roots = []
    if user_dir:
        roots.append(Path(user_dir))
    if game.kind == "modules" and programdata:
        roots.append(Path(programdata) / game.user_dir_name)
    found = []

    def take(d, label):
        try:
            for f in d.iterdir():
                if f.is_file() and f.suffix.lower() in TEXT_EXT and not any(s in f.name.lower() for s in SKIP_NAMES):
                    st = f.stat()
                    found.append({"path": f, "label": label, "mtime": st.st_mtime, "size": st.st_size})
        except OSError:
            pass

    for r in roots:
        take(r / "logs", "log")
        crashes = r / "crashes"
        try:
            dirs = sorted((d for d in crashes.iterdir() if d.is_dir()), key=lambda d: d.stat().st_mtime, reverse=True)
        except OSError:
            dirs = []
        if dirs:
            take(dirs[0], "crash")
        take(crashes, "crash")
    found.sort(key=lambda f: -f["mtime"])
    return found[:MAX_FILES]


def read_tail(path, limit=MAX_TAIL):
    """The last `limit` bytes of a text file as lines (HTML is reduced to its text)."""
    try:
        with open(path, "rb") as f:
            f.seek(0, os.SEEK_END)
            size = f.tell()
            f.seek(max(0, size - limit))
            raw = f.read()
    except OSError:
        return []
    text = raw.decode("utf-8", errors="replace")
    if Path(path).suffix.lower() in (".html", ".htm"):
        text = re.sub(r"<(script|style).*?</\1>", " ", text, flags=re.S | re.I)
        text = re.sub(r"<br\s*/?>|</(p|div|li|tr|h\d)>", "\n", text, flags=re.I)
        text = re.sub(r"<[^>]+>", " ", text)
    return [l.strip() for l in text.splitlines() if l.strip()]


class _Index:
    """Which mod a log line is about."""

    def __init__(self, mods, ids):
        self.by_folder, self.by_rid, self.names = {}, {}, []
        for mid in ids:
            m = mods.get(mid)
            if not m:
                continue
            base = Path(str(m.get("root") or "")).name.lower()
            if base:
                self.by_folder.setdefault(base, mid)
            if m.get("remote_id"):
                self.by_rid[str(m["remote_id"])] = mid
            nm = str(m.get("name") or "").lower()
            if len(nm) >= 8:
                self.names.append((nm, mid))

    def mods_in(self, line, use_names=True):
        low = line.lower()
        hit = []
        for tok in PATH_RE.findall(line):
            t = tok.lower()
            t = t[:-4] if t.endswith(".mod") else t
            mid = self.by_folder.get(t)
            if not mid:
                u = UGC_RE.fullmatch(t)
                mid = self.by_rid.get(u.group(1)) if u else None
            if mid and mid not in hit:
                hit.append(mid)
        for rid in UGC_RE.findall(line) + ID_RE.findall(line):
            mid = self.by_rid.get(rid)
            if mid and mid not in hit:
                hit.append(mid)
        if not hit and use_names:
            hit = [mid for nm, mid in self.names if nm in low][:3]
        return hit


def _shape(line):
    """A line without its numbers and time stamps, so repeats of one message count once."""
    s = re.sub(r"\[\d\d:\d\d:\d\d\]|\d{4}-\d\d-\d\d[ T]\d\d:\d\d:\d\d(?:[.,]\d+)?", "", line)
    return re.sub(r"\d+", "#", s).strip()[:200]


def analyse(game, mods, enabled, issues, changed, files, now=None):
    """-> {logs, reasons, suspects, newest, notes}. `files` is the output of log_files; `issues` are the app's own
    load-order findings; `changed` maps a mod id to why it counts as recently changed."""
    now = time.time() if now is None else now
    idx = _Index(mods, enabled)
    enabled_set = set(enabled)
    texts, logs = [], []
    for f in files:
        lines = read_tail(f["path"])[-MAX_LINES:]
        texts.append((f, lines))
        logs.append({"name": f["path"].name, "where": gamelog.redact(str(f["path"].parent)), "kind": f["label"],
                     "modified": f["mtime"], "lines": len(lines)})
    score, seen, info = {}, {}, {}

    def add(mid, pts, why, sample=None, key=None, kind="log"):
        d = info.setdefault(mid, {"errors": 0, "warnings": 0, "samples": [], "why": []})
        k = (mid, key or why)
        if k in seen:
            seen[k] += 1
            score[mid] = score.get(mid, 0) + (0.25 if seen[k] <= 20 else 0)
            return
        seen[k] = 1
        score[mid] = score.get(mid, 0) + pts
        if kind == "error":
            d["errors"] += 1
        elif kind == "warn":
            d["warnings"] += 1
        if sample and len(d["samples"]) < 3:
            d["samples"].append(gamelog.redact(sample[:240]))
        if why and why not in d["why"] and kind not in ("error", "warn"):
            d["why"].append(why)

    for f, lines in texts:
        tail_from = max(0, len(lines) - 60)   # what is written just before the end is closest to the crash
        for n, line in enumerate(lines):
            is_err = ERR.search(line)
            if not is_err and not WARN.search(line):
                continue
            mids = [m for m in idx.mods_in(line, use_names=bool(is_err)) if m in enabled_set]
            if not mids:
                continue
            near = 2 if (n >= tail_from or f["label"] == "crash") else 1
            for mid in mids:
                add(mid, (3 if is_err else 1) * near, "", sample=line, key=_shape(line), kind="error" if is_err else "warn")

    for i in issues:   # the app's own findings
        mid = i.get("module")
        if mid in enabled_set and i.get("code") in ("missing_dependency", "disabled_dependency", "incompatible", "version_mismatch",
                                                    "cycle", "missing_module", "metadata_error", "wrong_order"):
            add(mid, 2 if i.get("severity") == "error" else 1, i.get("message", ""), key=i.get("code"))
    for mid, why in changed.items():
        if mid in enabled_set:
            add(mid, 1.5, why, key="changed")

    suspects = []
    for mid, s in sorted(score.items(), key=lambda kv: -kv[1])[:MAX_SUSPECTS]:
        if s <= 0:
            continue
        d = info[mid]
        if d["errors"]:
            d["why"].insert(0, f"named in {d['errors']} error line{'' if d['errors'] == 1 else 's'} of the game's logs")
        if d["warnings"]:
            d["why"].insert(1 if d["errors"] else 0, f"named in {d['warnings']} warning line{'' if d['warnings'] == 1 else 's'}")
        suspects.append({"id": mid, "name": mods[mid]["name"], "score": round(s, 1), "errors": d["errors"],
                         "warnings": d["warnings"], "why": d["why"], "samples": d["samples"],
                         "in_logs": bool(d["errors"] or d["warnings"])})
    for i, x in enumerate(suspects):   # "high" only for a clear leader that the logs themselves name
        nxt = suspects[i + 1]["score"] if i + 1 < len(suspects) else 0
        x["level"] = "high" if i == 0 and x["in_logs"] and x["score"] >= 6 and x["score"] >= 1.5 * nxt else \
                     "medium" if x["in_logs"] or x["score"] >= 3 else "low"

    blob = [(f, l) for f, lines in texts for l in lines]
    reasons = []
    for pat, kind, title, advice in SIGNATURES:
        hit = next((l for f, l in reversed(blob) if pat.search(l)), None)
        if hit:
            m = pat.search(hit)
            evidence = gamelog.redact(hit[:240])
            extra = f" ({m.group(1)})" if kind == "assembly" and m.groups() else ""
            reasons.append({"kind": kind, "title": title + extra, "advice": advice, "evidence": evidence})
    newest = max((f["mtime"] for f in files), default=None)
    notes = []
    if not files:
        notes.append("No game logs were found. Start the game, let it crash, then press Diagnose again.")
    elif newest and now - newest > 3 * 86400:
        notes.append("The newest log is more than 3 days old, so it may not be about your last crash.")
    if files and not reasons and not any(s["in_logs"] for s in suspects):
        notes.append("The logs name no mod and no known crash cause. Try Launch part on the Load order tab: start with half of the mods and keep halving to find the one.")
    return {"logs": logs, "reasons": reasons, "suspects": suspects, "newest": newest, "notes": notes}
