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
    load_style: str              # "descriptor": mod/ugc_<id>.mod entries; "path": mod folder / workshop path;
                                 # "enabled_paths": {"enabledMods": [{"path": <absolute mod folder>}]} (Victoria 3)
    def_dirs: tuple              # script folders whose top-level keys are definitions
    vanilla_only: tuple = ()     # only these folders under <install>/game hold base content (empty = all)
    theme: dict = field(default_factory=dict)
    verified: bool = False       # True once a real install confirmed the load file + layout
    kind: str = "paradox"        # "paradox": playsets write a load file; "modules": Bannerlord-style modules (SubModule.xml)
    user_parent: str = "Paradox Interactive"  # folder in Documents that holds user_dir_name ("" = directly in Documents)
    seed_mods: tuple = ()        # module ids a new playset starts with (the official modules of a "modules" game)
    exe_rel: tuple = ()          # game executable relative to the install root ("modules" games start it themselves)
    launch_prefix: tuple = ()    # arguments before the module list
    content_dir: object = None   # folder under the install root that holds the base content ("" = the root itself); None = the kind's default
    custom: bool = False         # made by the user in the app (beta), not built in
    playsets_file: str = ""      # the game's own playset list in the user dir; its active playset is what the game starts with
    saves_dir: str = ""          # save folder in the user dir that a playset can have its own copy of ("" = the kind's default)

    @property
    def vanilla_dir_name(self):
        if self.content_dir is not None:
            return self.content_dir
        return "game" if self.kind == "paradox" else "Modules"

    @property
    def has_conflicts(self):
        """File/definition conflict analysis only makes sense for the Paradox games' shared script folders."""
        return self.kind == "paradox"

    @property
    def saves_dir_name(self):
        """The folder in the user dir the game reads its saves from; "" when this app does not switch saves."""
        return self.saves_dir or ("save games" if self.kind == "paradox" else "")

    @property
    def has_saves(self):
        return bool(self.saves_dir_name)

    @property
    def has_launcher_import(self):
        return True

    def public(self):
        """What the browser needs to know."""
        return {"id": self.id, "name": self.name, "app_id": self.app_id, "load_file": self.load_file,
                "theme": self.theme, "verified": self.verified, "kind": self.kind,
                "has_conflicts": self.has_conflicts, "has_saves": self.has_saves,
                "install_marker": "/".join(self.install_marker), "custom": self.custom,
                "saves_dir": self.saves_dir_name}


_COMMON = {"--ink": "#efe6d4", "--mut": "#a1928f"}

CK3 = Game(
    id="ck3", name="Crusader Kings III", app_id="1158310", user_dir_name="Crusader Kings III",
    install_dir_name="Crusader Kings III", install_marker=("game", "common"),
    load_file="dlc_load.json", load_style="descriptor", def_dirs=("common", "events"), verified=True,
    theme={**_COMMON, "--bg": "#120b0b", "--side": "#170e0e", "--panel": "#1d1313", "--line": "#3b2423",
           "--acc": "#e0766a", "--accink": "#fff4ee", "--p1": "#8f2a24", "--p2": "#b53a32", "--p3": "#6b1e1a",
           "--mut": "#a08c85"})

EU5 = Game(
    id="eu5", name="Europa Universalis V", app_id="3450310", user_dir_name="Europa Universalis V",
    install_dir_name="Europa Universalis V", install_marker=("game", "in_game"),
    load_file="dlc_load.json", load_style="path", def_dirs=("common",),
    vanilla_only=("in_game", "main_menu", "loading_screen"), playsets_file="playsets.json", verified=True,
    theme={**_COMMON, "--bg": "#0e1621", "--side": "#0b121b", "--panel": "#15202d", "--line": "#2a3a4d",
           "--acc": "#d4a73a", "--accink": "#1a1407", "--p1": "#2b4a6e", "--p2": "#3a6291", "--p3": "#223a56",
           "--mut": "#8f9bab"})

# Victoria 3's launcher writes content_load.json as {"enabledMods": [{"path": "<absolute folder>"}], "enabledUGC": [],
# "disabledDLC": []}, with no mod/ugc_<id>.mod stubs (seen on a real install, docs/22-checked-on-a-real-pc.md).
VIC3 = Game(
    id="vic3", name="Victoria 3", app_id="529340", user_dir_name="Victoria 3",
    install_dir_name="Victoria 3", install_marker=("game", "common"),
    load_file="content_load.json", load_style="enabled_paths", def_dirs=("common", "events"),
    theme={**_COMMON, "--bg": "#0f0b0d", "--side": "#150e12", "--panel": "#1e1519", "--line": "#3a2a31",
           "--acc": "#d4b883", "--accink": "#fbf3e2", "--p1": "#8c3a58", "--p2": "#a34868", "--p3": "#6a2640"})

# Mount & Blade II: Bannerlord. Mods are "modules" (a folder with SubModule.xml) in <install>/Modules and in the Steam
# Workshop folder; the game is started with the chosen module list on its command line. Everything here comes from
# other mod managers' code and is UNVERIFIED on a real install (docs/17-bannerlord.md).
BANNERLORD = Game(
    id="bannerlord", name="Mount & Blade II: Bannerlord", app_id="261550", user_dir_name="Mount and Blade II Bannerlord",
    user_parent="", install_dir_name="Mount & Blade II Bannerlord", install_marker=("Modules", "Native"),
    load_file="(command line)", load_style="modules", def_dirs=(), kind="modules",
    seed_mods=("Native", "SandBoxCore", "BirthAndDeath", "CustomBattle", "Sandbox", "StoryMode", "NavalDLC"),
    exe_rel=("bin", "Win64_Shipping_Client", "Bannerlord.exe"), launch_prefix=("/singleplayer",),
    saves_dir="Game Saves",   # Documents/Mount and Blade II Bannerlord/Game Saves (seen on a real PC; the switching is unverified)
    theme={**_COMMON, "--bg": "#0f120e", "--side": "#0b0e0a", "--panel": "#171c15", "--line": "#2f3a2b",
           "--acc": "#cfa84a", "--accink": "#1a1405", "--p1": "#4d6b3a", "--p2": "#65884a", "--p3": "#3a5229",
           "--mut": "#97a38f"})

# Four more Paradox games, added as data. Their folders, files and Steam ids come from Irony Mod Manager's game
# registrations (src/IronyModManager.Shared/Constants.cs, Services/Registrations/GameRegistration.cs and
# IO/Mods/Exporter/JsonExporter.cs), not from a real install of ours, so they are verified=False until Play is confirmed:
# - all four read `mod/*.mod` descriptors and take their enabled mods from dlc_load.json `enabled_mods` (like CK3);
# - Imperator keeps its content under game/ like CK3; EU4, HOI4 and Stellaris keep it straight in the install folder;
# - the install marker is a folder only that game has in Irony's folder list for it.
EU4 = Game(
    id="eu4", name="Europa Universalis IV", app_id="236850", user_dir_name="Europa Universalis IV",
    install_dir_name="Europa Universalis IV", install_marker=("missions",),
    load_file="dlc_load.json", load_style="descriptor", def_dirs=("common", "events", "decisions", "missions"),
    content_dir="", vanilla_only=("common", "customizable_localization", "decisions", "events", "history", "interface",
                                  "localisation", "map", "missions"),
    theme={**_COMMON, "--bg": "#0d1418", "--side": "#0a1014", "--panel": "#131d23", "--line": "#29404b",
           "--acc": "#7fb8c9", "--accink": "#061218", "--p1": "#2a5566", "--p2": "#356c80", "--p3": "#1f4150",
           "--mut": "#8fa2a9"})

HOI4 = Game(
    id="hoi4", name="Hearts of Iron IV", app_id="394360", user_dir_name="Hearts of Iron IV",
    install_dir_name="Hearts of Iron IV", install_marker=("portraits",),
    load_file="dlc_load.json", load_style="descriptor", def_dirs=("common", "events"),
    content_dir="", vanilla_only=("common", "events", "history", "interface", "localisation", "map"),
    theme={**_COMMON, "--bg": "#11120d", "--side": "#0d0e0a", "--panel": "#191b14", "--line": "#363a2a",
           "--acc": "#c9b26a", "--accink": "#171305", "--p1": "#5b5f3a", "--p2": "#717648", "--p3": "#45482b",
           "--mut": "#a09d8a"})

STELLARIS = Game(
    id="stellaris", name="Stellaris", app_id="281990", user_dir_name="Stellaris",
    install_dir_name="Stellaris", install_marker=("prescripted_countries",),
    load_file="dlc_load.json", load_style="descriptor", def_dirs=("common", "events"),
    content_dir="", vanilla_only=("common", "events", "flags", "interface", "localisation", "map", "prescripted_countries"),
    theme={**_COMMON, "--bg": "#0a0f1a", "--side": "#080c15", "--panel": "#111a2a", "--line": "#253552",
           "--acc": "#6fc3e8", "--accink": "#04121a", "--p1": "#27507a", "--p2": "#30659a", "--p3": "#1d3d5e",
           "--mut": "#8e9bb0"})

IMPERATOR = Game(
    id="imperator", name="Imperator: Rome", app_id="859580", user_dir_name="Imperator",
    install_dir_name="ImperatorRome", install_marker=("game", "setup"),
    load_file="dlc_load.json", load_style="descriptor", def_dirs=("common", "events", "decisions"),
    theme={**_COMMON, "--bg": "#140d0c", "--side": "#100a09", "--panel": "#1c1312", "--line": "#3d2724",
           "--acc": "#d9a35a", "--accink": "#1a1004", "--p1": "#7a3a2a", "--p2": "#934733", "--p3": "#5c2b1f",
           "--mut": "#a8958c"})

GAMES = {g.id: g for g in (CK3, EU5, VIC3, BANNERLORD, EU4, HOI4, STELLARIS, IMPERATOR)}
DEFAULT_GAME = "ck3"


def get(game_id):
    try:
        return GAMES[game_id]
    except KeyError:
        raise ValueError(f"Unknown game '{game_id}'. Supported: {', '.join(GAMES)}")
