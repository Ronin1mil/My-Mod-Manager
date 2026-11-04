"""A stand-in for Random New World's command line, for tests (the real program is a Windows program).

Prints what the real commands print, from RNW's open-source code: JSON on stdout, progress lines on stderr.
Configured by environment variables: RNW_STUB_MODS (the profile's mod folder), RNW_STUB_WORLDS (a JSON file for `worlds`),
RNW_STUB_CODE (the code `world-code` and `world` use), RNW_STUB (ok | fail | hang | junk).
"""
import json
import os
import shutil
import sys
import time
from pathlib import Path

args = sys.argv[1:]
mode = os.environ.get("RNW_STUB", "ok")
mods = Path(os.environ.get("RNW_STUB_MODS", "."))
code = os.environ.get("RNW_STUB_CODE", "")


def mod(world_id, name="RNW: Continents TEST"):
    d = mods / f"rnw_exp_world_{world_id}"
    (d / ".metadata/rnw-library").mkdir(parents=True, exist_ok=True)
    (d / "in_game/map_data").mkdir(parents=True, exist_ok=True)
    (d / ".metadata/metadata.json").write_text(json.dumps({"name": name, "version": "1.1.0", "short_description": f"A world. {code}"}))
    (d / ".metadata/rnw-library/world.json").write_text(json.dumps({
        "schema": 1, "id": world_id, "code": code, "preset": "continents", "seed": 42, "generator": "1.1.0", "game_build": "26300913",
        "created": int(time.time()), "seconds": 90.5, "name": "", "notes": "", "record": {"seed": 42, "settings": {"new_world": {"land_permille": 350}}}}))
    return d


if mode == "junk":
    print("this is not json")
    sys.exit(0)
if not args:
    sys.exit(2)
cmd = args[0]
if cmd == "worlds":
    print(Path(os.environ["RNW_STUB_WORLDS"]).read_text())
elif cmd == "world-code":
    print(json.dumps({"code": code, "preset": args[2] if len(args) > 2 else "continents", "seed": 42}))
elif cmd == "world":
    if mode == "hang":
        print("[ 5%] start Reading the game", file=sys.stderr, flush=True)
        time.sleep(60)
    if mode == "fail":
        print("[ 5%] start Reading the game", file=sys.stderr, flush=True)
        print("Error: not enough free memory (7.5 GB needed)", file=sys.stderr)
        sys.exit(2)
    for pct, label in ((10, "Reading the game"), (60, "Making the land"), (100, "Writing the mod")):
        print(f"[{pct:3d}%] start {label}", file=sys.stderr, flush=True)
        print(f"[{pct:3d}%] done  {label}", file=sys.stderr, flush=True)
    d = mod("abcde23456")
    print(json.dumps({"code": code, "bundle": str(d), "installed": str(d), "copied_to": None, "seconds": 1.5, "summary": {"locations": 123, "land": "35 %"}}, indent=2))
elif cmd == "add-world":
    d = mod(args[1][-10:] if len(args[1]) >= 10 else "zzzzzzzzzz")
    print(json.dumps({"world": args[1], "installed": str(d)}))
elif cmd == "remove-world":
    shutil.rmtree(mods / f"rnw_exp_world_{args[1]}", ignore_errors=True)
    print(json.dumps({"removed": args[1]}))
else:
    print("Error: unknown command", file=sys.stderr)
    sys.exit(2)
