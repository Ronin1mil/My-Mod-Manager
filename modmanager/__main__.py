import argparse

from modmanager import __version__, games

ap = argparse.ArgumentParser(prog="modmanager", description="Mod manager for Paradox grand strategy games")
ap.add_argument("--game", choices=list(games.GAMES), help="open this game first; per-game flags below apply to it")
ap.add_argument("--port", type=int, default=8765)
ap.add_argument("--user-dir", help="user data dir of --game (auto-detected by default)")
ap.add_argument("--workshop-dir", help="Steam workshop content dir of --game (auto-detected)")
ap.add_argument("--game-dir", help="install dir of --game (auto-detected); used for the version and base-game comparison")
ap.add_argument("--logo", help="image shown in the header (png/jpg/webp/svg); default: logo.* in the game's config folder")
ap.add_argument("--game-exe", help="launch this executable directly instead of going through Steam")
ap.add_argument("--game-version", help="override the game version used for compatibility warnings, e.g. 1.7.6")
ap.add_argument("--fetch-logo", action="store_true", help="download --game's logo from Steam's CDN once (explicit network access)")
ap.add_argument("--check-update", action="store_true", help="check GitHub for a newer version and exit")
ap.add_argument("--list-games", action="store_true", help="list supported games and exit")
ap.add_argument("--version", action="store_true", help="print the version and exit")
ap.add_argument("--no-browser", action="store_true")
a = ap.parse_args()

if a.version:
    print(__version__)
    raise SystemExit(0)
if a.list_games:
    for g in games.GAMES.values():
        print(f"{g.id:5} {g.name}  (Steam app {g.app_id}, load file {g.load_file})")
    raise SystemExit(0)
if a.check_update:
    from modmanager.update import check_for_update
    r = check_for_update()
    print(f"{r['message']} (running {r['current']}" + (f", latest {r['latest']}" if r["latest"] else "") + f")\n{r['url']}")
    raise SystemExit(0 if r["status"] in ("update", "current", "no_releases") else 1)

per_game = {"user_dir": a.user_dir, "workshop_dir": a.workshop_dir, "game_dir": a.game_dir,
            "game_version_": a.game_version, "game_exe": a.game_exe, "logo": a.logo}
per_game = {k: v for k, v in per_game.items() if v}
if (per_game or a.fetch_logo) and not a.game:
    ap.error("--user-dir, --workshop-dir, --game-dir, --game-exe, --logo, --game-version and --fetch-logo need --game")
if a.fetch_logo:
    from modmanager.paths import fetch_logo
    print("Saved", fetch_logo(games.get(a.game)))

from modmanager.server import serve
serve(a.port, not a.no_browser, overrides={a.game: per_game} if a.game else None, initial_game=a.game)
