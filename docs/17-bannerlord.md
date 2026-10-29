# Mount & Blade II: Bannerlord

Bannerlord does not use Paradox's load files or `.mod` descriptors. Everything below comes from the open-source Bannerlord tooling of other mod managers and has **not been checked against a real install** (`verified` stays false; the app says so).

## What a mod is
A **module**: a folder with a `SubModule.xml`. Modules live in
- `<install>/Modules/<ModuleId>/` (manual installs, Nexus), and
- `steamapps/workshop/content/261550/<workshop id>/` (each Workshop item folder is itself a module).

If the same module id exists in both places the `Modules` copy wins, as in the game. Module ids may only contain letters, digits, `_`, `.` and `-` because they go onto the game's command line; anything else is ignored.

## What is read from SubModule.xml
| Element | Meaning here |
|---|---|
| `Id`, `Name`, `Version` | identity, shown name, version |
| `Official`, or an official id (`Native`, `SandBoxCore`, `Sandbox`, `StoryMode`, `CustomBattle`, `BirthAndDeath`, `NavalDLC`) | official modules load first and cannot be uninstalled |
| `DependedModules/DependedModule Id` | required: must be in the playset and load before this module |
| `DependedModule Optional="true"`, `OptionalDependModule` | loads before this module **only if present**; never a warning |
| `DependedModuleMetadata id order=LoadBeforeThis` (`optional`) | same as above (required unless `optional`) |
| `DependedModuleMetadata order=LoadAfterThis`, `ModulesToLoadAfterThis/Module` | those modules load after this one, if present |
| `IncompatibleModules/Module`, `DependedModuleMetadata incompatible="true"` | Warnings: "incompatible, disable one" |

Not used: version ranges (`DependentVersion`, `version=`), `RequiredGameVersion` and `LoadAfterModules` (its direction is ambiguous). No game-version warnings are raised for this game.

## Playsets
A new playset starts with the official modules (`Native`, `SandBoxCore`, `CustomBattle`, `Sandbox`, `StoryMode`) in that order. **Auto-sort** keeps dependencies first and official modules ahead of the rest; your own order is kept wherever no rule applies. The Conflicts tab, base-game comparison and the save-version/own-save-folder features are not offered: modules do not share script folders, and their saves are handled by the game.

## Play
No file is written. The game is started directly, with the same arguments other launchers use:
`<install>/bin/Win64_Shipping_Client/Bannerlord.exe /singleplayer _MODULES_*Native*SandBoxCore*…*_MODULES_ <your extra arguments>`
The enabled modules of the playset (or the part chosen under **Launch part…**) go into the list in playset order. Steam must be running. If the executable is somewhere else (a different launcher such as BLSE), pass `--game-exe`.

## Installing
**Install mod…** takes a `.zip` / `.tar*` that contains a module (with or without a `Modules/` wrapper) and puts it in `<install>/Modules/<ModuleId>`; an existing copy is moved to the backup folder first. Official modules are never replaced or uninstalled. Workshop modules are installed and updated by Steam.

## Import
The launcher's last module selection (`Documents/Mount and Blade II Bannerlord/Configs/LauncherData.xml`, `<UserModData><Id/><IsSelected/>`) can be imported from the Import menu as one playset ("Launcher selection"); unselected modules stay in it, switched off; modules that are not installed are reported.

## To verify on a real PC
1. The install is found (Steam library, or paste any path inside it) and the version in the corner matches the game.
2. The Library lists your modules (Modules folder and Workshop).
3. Play starts the game with exactly the playset's modules in the launcher's *Mods* list or in-game.
4. `LauncherData.xml` import shows the modules you had selected.
