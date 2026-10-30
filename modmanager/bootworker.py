"""Start-up helper: a few processes, each working out a share of the playsets (see `split`), so the conflict checks run
side by side on separate cores instead of one after another (Python threads cannot do that: the comparing is pure
Python and holds the GIL).

The app starts `python -I -c <RUN> <folder holding the modmanager package>` (see `start`), writes a pickled job from
GameApp.warm_job to its stdin and reads the pickled answer from its stdout; progress lines come on stderr. The worker
only reads mod files and the parse cache, it never writes anything, so it cannot race the app over a file.
"""
import os
import pickle
import subprocess
import sys
import time
from pathlib import Path

from . import scan

RUN = "import sys; sys.path.insert(0, sys.argv[1]); from modmanager.bootworker import main; main()"


def run(job, say=lambda _t: None):
    """Work out every playset in `job`; -> {results: [one summary per playset], files, trusted, entries}."""
    scan.load_cache(job["cache"])
    files, trusted, results = {}, set(), []
    for ps in job["playsets"]:
        t = time.time()
        conflicts = scan.find_conflicts(job["mods"], ps["order"], files, job["defs"], ps["vanilla"], trusted=trusted)
        results.append(scan.summarize(conflicts))
        say(f'playset "{ps["name"]}" checked ({time.time() - t:.1f} s)')
    return {"results": results, "files": files, "trusted": trusted, "entries": scan.fresh_entries()}


def main():
    job = pickle.load(sys.stdin.buffer)

    def say(text):
        sys.stderr.write(text + "\n")
        sys.stderr.flush()

    answer = run(job, say)
    pickle.dump(answer, sys.stdout.buffer, protocol=pickle.HIGHEST_PROTOCOL)
    sys.stdout.buffer.flush()


def worker_count():
    """How many workers at once. Measured on an 8-core Ryzen with 33 playsets in 3 games: 1 process per game 26 s
    (CK3 alone holds it up), 5-7 processes ~18 s, more than that no faster (each one also loads the parse cache)."""
    return max(2, min(6, (os.cpu_count() or 2) // 2))


def split(jobs, k):
    """Spread the playsets of these jobs (one per game) over about `k` workers, a game's share in proportion to its work
    (a mod costs about the same everywhere; each playset also has a fixed cost). -> [(index into jobs, smaller job)]"""
    cost = lambda ps: len(ps["order"]) + 10
    total = sum(cost(ps) for j in jobs for ps in j["playsets"]) or 1
    out = []
    for n, j in enumerate(jobs):
        mine = sum(cost(ps) for ps in j["playsets"])
        parts = max(1, min(len(j["playsets"]), round(k * mine / total)))
        buckets, load = [[] for _ in range(parts)], [0] * parts
        for ps in sorted(j["playsets"], key=cost, reverse=True):   # biggest first, each to the least loaded worker
            i = load.index(min(load))
            buckets[i].append(ps)
            load[i] += cost(ps)
        out += [(n, {**j, "playsets": b}) for b in buckets]
    return out


def usable():
    """Workers need a real Python to start; the frozen Windows exe has none (it then checks the games one by one)."""
    return not getattr(sys, "frozen", False) and bool(sys.executable) and os.environ.get("MODMANAGER_BOOT_PROCS") != "0"


def python():
    """The interpreter for a worker: python.exe rather than pythonw.exe (which has no standard streams of its own)."""
    exe = Path(sys.executable)
    if exe.name.lower() == "pythonw.exe" and (exe.parent / "python.exe").is_file():
        return str(exe.parent / "python.exe")
    return str(exe)


def start(job):
    """Start a worker for one job; returns the Popen (stdin already written and closed, so it is working)."""
    root = str(Path(__file__).resolve().parent.parent)   # the source folder, or the .pyzw file itself
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)   # no console window flashing up, even from python.exe
    p = subprocess.Popen([python(),"-I", "-c", RUN, root], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                         stderr=subprocess.PIPE, creationflags=flags)
    try:
        pickle.dump(job, p.stdin, protocol=pickle.HIGHEST_PROTOCOL)
        p.stdin.close()
    except OSError:
        p.kill()
        raise
    return p
