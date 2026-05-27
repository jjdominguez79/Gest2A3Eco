; =============================================================================
; Script de instalacion Inno Setup para Gest2A3Eco
; Herramienta requerida: Inno Setup 6.x  ->  https://jrsoftware.org/isinfo.php
;
; IMPORTANTE: Antes de compilar este script, generar el .exe con PyInstaller:
;   pyinstaller Gest2A3Eco.spec
; Los archivos fuente del instalador son los que quedan en dist\Gest2A3Eco\
;
; Compilar:
;   iscc.exe setup.iss
; o abrir con el IDE de Inno Setup y pulsar F9.
;
; El instalador resultante se guarda en dist_installer\Setup_Gest2A3Eco_X.Y.Z.exe
; =============================================================================

#define MyAppName      "Gest2A3Eco"
#define MyAppVersion   "1.1.1"
#define MyAppPublisher "Asesoria Gestinem S.L."
#define MyAppURL       "https://www.gestinem.es"
#define MyAppExeName   "Gest2A3Eco.exe"

; GUID unico de la aplicacion. NO cambiar entre versiones (identifica la app para el desinstalador).
#define MyAppId        "{{C4F89A23-7B1D-4E5F-A839-D2C650FAB918}}"

[Setup]
AppId={#MyAppId}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppVerName={#MyAppName} {#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}
AppUpdatesURL={#MyAppURL}

; Directorio de instalacion por defecto: C:\Program Files\Gestinem\Gest2A3Eco
DefaultDirName={autopf}\Gestinem\Gest2A3Eco
DefaultGroupName=Gestinem\Gest2A3Eco

; Opciones de UI del asistente
AllowNoIcons=yes
WizardStyle=modern
DisableDirPage=yes
DisableProgramGroupPage=yes

; Compilacion del paquete
Compression=lzma2/ultra64
SolidCompression=yes
OutputDir=dist_installer
OutputBaseFilename=Setup_{#MyAppName}_{#MyAppVersion}
; SetupIconFile=icono.ico

; Permisos: requiere administrador (necesario para instalar en Program Files)
PrivilegesRequired=admin
PrivilegesRequiredOverridesAllowed=dialog

; Cierre automatico de la aplicacion si esta en ejecucion
CloseApplications=yes
CloseApplicationsFilter=*{#MyAppExeName}
RestartIfNeededByRun=no

; Informacion para Agregar o quitar programas
UninstallDisplayName={#MyAppName}
UninstallDisplayIcon={app}\{#MyAppExeName}

[Languages]
Name: "spanish"; MessagesFile: "compiler:Languages\Spanish.isl"

[Tasks]
; Icono de escritorio (opcional, desmarcado por defecto)
Name: "desktopicon"; Description: "Crear icono en el escritorio"; \
  GroupDescription: "Iconos adicionales:"; Flags: unchecked

[Files]
; -------------------------------------------------------------------------
; Archivos de la aplicacion generados por PyInstaller.
; Se excluye la carpeta plantillas/ para preservar la base de datos SQLite
; y la configuracion del usuario entre actualizaciones.
; -------------------------------------------------------------------------
Source: "dist\Gest2A3Eco\*"; DestDir: "{app}"; \
  Flags: ignoreversion recursesubdirs createallsubdirs; \
  Excludes: "plantillas,plantillas\*"

[Icons]
; Acceso directo en el Menu Inicio
Name: "{group}\{#MyAppName}"; \
  Filename: "{app}\{#MyAppExeName}"; \
  IconFilename: "{app}\{#MyAppExeName}"; \
  Comment: "Gestionar facturas y generar archivos A3ECO"

; Desinstalador en el Menu Inicio
Name: "{group}\Desinstalar {#MyAppName}"; Filename: "{uninstallexe}"

; Acceso directo en el Escritorio (solo si la tarea esta seleccionada)
Name: "{autodesktop}\{#MyAppName}"; \
  Filename: "{app}\{#MyAppExeName}"; \
  IconFilename: "{app}\{#MyAppExeName}"; \
  Tasks: desktopicon; \
  Comment: "Gestionar facturas y generar archivos A3ECO"

[Run]
; Ofrecer iniciar la aplicacion al terminar la instalacion
Filename: "{app}\{#MyAppExeName}"; \
  Description: "Iniciar {#MyAppName} ahora"; \
  Flags: nowait postinstall skipifsilent

[InstallDelete]
; Limpiar los archivos binarios de PyInstaller de la instalacion anterior
; para evitar conflictos con DLLs y .pyd obsoletos.
; La carpeta plantillas/ y config.json NO se tocan (datos del usuario).
Type: filesandordirs; Name: "{app}\_internal"

[UninstallDelete]
; Al desinstalar, eliminar binarios pero respetar datos del usuario
Type: filesandordirs; Name: "{app}\_internal"

[Code]
// =========================================================================
// Verificar sistema operativo minimo: Windows 10
// =========================================================================
function InitializeSetup(): Boolean;
var
  Version: TWindowsVersion;
begin
  GetWindowsVersionEx(Version);
  if Version.Major < 10 then
  begin
    MsgBox(
      'Gest2A3Eco requiere Windows 10 o superior.' + #13#10 +
      'La instalacion se cancelara.',
      mbError, MB_OK
    );
    Result := False;
    Exit;
  end;
  Result := True;
end;

// =========================================================================
// Mensaje informativo al actualizar (cuando ya hay una version instalada)
// =========================================================================

procedure CurPageChanged(CurPageID: Integer);
begin
  if CurPageID = wpWelcome then
  begin
    if WizardForm.WelcomeLabel2 <> nil then
    begin
      WizardForm.WelcomeLabel2.Caption :=
        'Esta instalacion actualizara Gest2A3Eco a la version {#MyAppVersion}.' + #13#10#13#10 +
        'Los datos de la aplicacion (base de datos, configuracion) se conservaran.' + #13#10#13#10 +
        'Se recomienda cerrar la aplicacion antes de continuar.';
    end;
  end;
end;
