; flywheel.iss - the Flywheel Windows installer (Inno Setup 6).
;
; One artifact a user can run: installs the app, the frozen engine
; (engine\flywheel-gateway.exe, launched by the app on demand), and the
; VC++ runtime DLLs, with a Start-menu entry and a clean uninstall.
; Build with scripts\build_installer.ps1, which stages the payloads and
; passes their locations; the defines below are its defaults so the script
; and a bare ISCC run agree.
;
; Payload locations are overridable: ISCC /DAppDir=... /DEngineDir=...
; /DCrtDir=... /DAppVersion=...

#ifndef AppVersion
  #define AppVersion "0.2.0"
#endif
#ifndef AppDir
  #define AppDir "..\build\windows\x64\runner\Release"
#endif
#ifndef EngineDir
  #define EngineDir "..\build\engine\flywheel-gateway"
#endif
#ifndef CrtDir
  #define CrtDir "..\build\crt"
#endif

#define MyAppName "Flywheel"
#define MyAppPublisher "ZentropyLabs"
#define MyAppExeName "flywheel_desktop.exe"

[Setup]
; AppId stays fixed across versions so upgrades replace, never duplicate.
AppId={{ecf4cc9b-8a7a-4de2-8e70-0f1ea0f17e5c}
AppName={#MyAppName}
AppVersion={#AppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}
UninstallDisplayIcon={app}\{#MyAppExeName}
OutputDir=..\build\installer
OutputBaseFilename=Flywheel-Setup-{#AppVersion}-x64
SetupIconFile=..\windows\runner\resources\app_icon.ico
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
; Per-user by default (no elevation); the dialog lets an admin choose
; all-users. Either way the uninstall entry is honest.
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; \
  GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
; The Flutter release bundle (app exe, flutter_windows.dll, data\).
Source: "{#AppDir}\*"; DestDir: "{app}"; \
  Flags: ignoreversion recursesubdirs createallsubdirs
; The frozen engine: the app launches {app}\engine\flywheel-gateway.exe by
; absolute path, so a clean machine needs no Python and no PATH setup.
Source: "{#EngineDir}\*"; DestDir: "{app}\engine"; \
  Flags: ignoreversion recursesubdirs createallsubdirs
; VC++ runtime beside the exe (redistributable copies from the VS Redist
; tree, never from System32).
Source: "{#CrtDir}\msvcp140.dll"; DestDir: "{app}"; Flags: ignoreversion
Source: "{#CrtDir}\vcruntime140.dll"; DestDir: "{app}"; Flags: ignoreversion
Source: "{#CrtDir}\vcruntime140_1.dll"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{group}\{cm:UninstallProgram,{#MyAppName}}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; \
  Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; \
  Description: "{cm:LaunchProgram,{#MyAppName}}"; \
  Flags: nowait postinstall skipifsilent
