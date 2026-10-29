"""Game profiles: everything that differs between the supported Paradox games, as data.

The engine (scan, order, store, server) never mentions a specific game. To support another game
add a `Game` here. Fields marked "unverified" are best knowledge, not confirmed on a real install;
docs/02-game-notes.md lists what to check and tests/test_games.py pins today's values.
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Game:
    id: str                      # short id used in URLs and config folders
    name: str                    # display name
    app_id: str                  # Steam app id (also the Workshop content folder name)
    user_dir_name: str           # folder under "Paradox Interactive" holding mod/, saves, load file
    install_dir_name: str        # default folder under steamapps/common
    install_marker: tuple        # path (relative to the install root) that proves it is this game
    load_file: str               # file in the user dir the game reads its enabled mods from
    load_style: str              # "descriptor": mod/ugc_<id>.mod entries; "path": mod folder / workshop path
    def_dirs: tuple              # script folders whose top-level keys are definitions
    vanilla_only: tuple = ()     # only these folders under <install>/game hold base content (empty = all)
    legacy_config: tuple = ()    # config folder names of the standalone managers this replaces
    theme: dict = field(default_factory=dict)
    verified: bool = False       # True once a real install confirmed the load file + layout

    @property
    def vanilla_dir_name(self):
        return "game"

    def public(self):
        """What the browser needs to know."""
        return {"id": self.id, "name": self.name, "app_id": self.app_id, "load_file": self.load_file,
                "theme": self.theme, "verified": self.verified,
                "install_marker": "/".join(self.install_marker)}


_COMMON = {"--ink": "#efe6d4", "--mut": "#a1928f"}

CK3 = Game(
    id="ck3", name="Crusader Kings III", app_id="1158310", user_dir_name="Crusader Kings III",
    install_dir_name="Crusader Kings III", install_marker=("game", "common"),
    load_file="dlc_load.json", load_style="descriptor", def_dirs=("common", "events"),
    legacy_config=("ck3mm",),
    theme={**_COMMON, "--bg": "#120b0b", "--side": "#170e0e", "--panel": "#1d1313", "--line": "#3b2423",
           "--acc": "#e0766a", "--accink": "#fff4ee", "--p1": "#8f2a24", "--p2": "#b53a32", "--p3": "#6b1e1a",
           "--mut": "#a08c85"})

EU5 = Game(
    id="eu5", name="Europa Universalis V", app_id="3450310", user_dir_name="Europa Universalis V",
    install_dir_name="Europa Universalis V", install_marker=("game", "in_game"),
    load_file="dlc_load.json", load_style="path", def_dirs=("common",),
    vanilla_only=("in_game", "main_menu", "loading_screen"), legacy_config=("eu5mm",),
    theme={**_COMMON, "--bg": "#0e1621", "--side": "#0b121b", "--panel": "#15202d", "--line": "#2a3a4d",
           "--acc": "#d4a73a", "--accink": "#1a1407", "--p1": "#2b4a6e", "--p2": "#3a6291", "--p3": "#223a56",
           "--mut": "#8f9bab"})

VIC3 = Game(
    id="vic3", name="Victoria 3", app_id="529340", user_dir_name="Victoria 3",
    install_dir_name="Victoria 3", install_marker=("game", "common"),
    load_file="content_load.json", load_style="descriptor", def_dirs=("common", "events"),
    legacy_config=("vic3mm",),
    theme={**_COMMON, "--bg": "#0f0b0d", "--side": "#150e12", "--panel": "#1e1519", "--line": "#3a2a31",
           "--acc": "#d4b883", "--accink": "#fbf3e2", "--p1": "#8c3a58", "--p2": "#a34868", "--p3": "#6a2640"})

GAMES = {g.id: g for g in (CK3, EU5, VIC3)}
DEFAULT_GAME = "ck3"


def get(game_id):
    try:
        return GAMES[game_id]
    except KeyError:
        raise ValueError(f"Unknown game '{game_id}'. Supported: {', '.join(GAMES)}")
