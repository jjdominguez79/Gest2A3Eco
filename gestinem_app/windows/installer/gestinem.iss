#define MyAppName "Gestinem"
#define MyAppVersion "0.1.1"
#define MyAppPublisher "Gestinem"
#define MyAppExeName "gestinem.exe"

[Setup]
AppId={{6D522A0D-07CF-47F7-875F-162EC47CBB38}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
SetupIconFile=..\runner\resources\app_icon.ico
DefaultDirName={localappdata}\Programs\Gestinem
DefaultGroupName=Gestinem
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
OutputDir=..\..\..\dist_installer
OutputBaseFilename=Gestinem-Windows-{#MyAppVersion}
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
UninstallDisplayIcon={app}\{#MyAppExeName}
CloseApplications=yes
RestartApplications=no

[Languages]
Name: "spanish"; MessagesFile: "compiler:Languages\Spanish.isl"

[Tasks]
Name: "desktopicon"; Description: "Crear un acceso directo en el escritorio"; GroupDescription: "Accesos directos:"; Flags: unchecked

[Files]
Source: "..\..\build\windows\x64\runner\Release\*"; DestDir: "{app}"; Excludes: "*.lib,*.exp"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\Gestinem"; Filename: "{app}\{#MyAppExeName}"
Name: "{autodesktop}\Gestinem"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Registry]
Root: HKCU; Subkey: "Software\Classes\es.gestinem.app"; ValueType: string; ValueName: ""; ValueData: "URL:Gestinem"; Flags: uninsdeletekey
Root: HKCU; Subkey: "Software\Classes\es.gestinem.app"; ValueType: string; ValueName: "URL Protocol"; ValueData: ""
Root: HKCU; Subkey: "Software\Classes\es.gestinem.app\shell\open\command"; ValueType: string; ValueName: ""; ValueData: """{app}\{#MyAppExeName}"" ""%1"""

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "Abrir Gestinem"; Flags: nowait postinstall skipifsilent
