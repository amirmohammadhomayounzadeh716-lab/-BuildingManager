; BuildingManager Windows installer (Inno Setup)
#define AppName "BuildingManager"
#if GetEnv("APP_VERSION") != ""
  #define AppVersion GetEnv("APP_VERSION")
#else
  #define AppVersion "18.8"
#endif
#define AppPublisher "Amir-Mohammad"
#define AppExeName "BuildingManager.exe"

[Setup]
AppId={{7E5B4A7C-9D1B-4B68-9E15-18A7D8C3F207}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher={#AppPublisher}
DefaultDirName={autopf}\{#AppName}
DefaultGroupName={#AppName}
UninstallDisplayIcon={app}\{#AppExeName}
OutputDir=dist
OutputBaseFilename=BuildingManager_Setup
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=admin
ArchitecturesInstallIn64BitMode=x64
SetupLogging=yes
CloseApplications=yes
RestartApplications=no

[Files]
Source: "dist\BuildingManager\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\{#AppName}"; Filename: "{app}\{#AppExeName}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExeName}"; Tasks: desktopicon

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; GroupDescription: "Additional icons:"

[Run]
Filename: "{app}\{#AppExeName}"; Description: "Launch BuildingManager"; Flags: postinstall nowait skipifsilent

; User data is stored in %USERPROFILE%\BuildingManagerData and is intentionally
; NOT removed by the uninstaller or by application upgrades.
