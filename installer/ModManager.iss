; Windows installer for Ronin Mod Manager (built by CI with Inno Setup: iscc /DAppVersion=x.y.z installer\ModManager.iss)
; Per-user install: no administrator rights needed, and the app can replace itself when it updates.
#ifndef AppVersion
  #define AppVersion "0.0.0"
#endif

[Setup]
AppId={{B3C0E1F2-7A55-4C3E-9D52-3C5A4E7D1A10}
AppName=Ronin Mod Manager
AppVersion={#AppVersion}
AppPublisher=Ronin1mil
AppPublisherURL=https://github.com/Ronin1mil/My-Mod-Manager
DefaultDirName={localappdata}\Programs\Ronin Mod Manager
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
OutputDir=..\dist
OutputBaseFilename=Mod-Manager-Setup
Compression=lzma2
SolidCompression=yes
UninstallDisplayIcon={app}\Mod-Manager.exe
SetupIconFile=icon.ico
WizardStyle=modern

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; Flags: unchecked

[Files]
Source: "..\dist\Mod-Manager-windows.exe"; DestDir: "{app}"; DestName: "Mod-Manager.exe"; Flags: ignoreversion

[Icons]
Name: "{autoprograms}\Ronin Mod Manager"; Filename: "{app}\Mod-Manager.exe"
Name: "{autodesktop}\Ronin Mod Manager"; Filename: "{app}\Mod-Manager.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\Mod-Manager.exe"; Description: "Start Ronin Mod Manager"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
; leftovers of an in-app update (the previous version is kept as .old until the next start)
Type: files; Name: "{app}\*.old"
Type: files; Name: "{app}\*.new"
