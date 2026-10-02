# Publicar Gestinem Flutter

Esta es la guía operativa única para Web, Android, Windows, iOS y macOS. Todos
los comandos se ejecutan desde `gestinem_app`.

## Qué comando necesito

| Objetivo | Bash / Warp | PowerShell | Resultado |
|---|---|---|---|
| Publicar la web | `bash tool/build_production.sh web` | `.\tool\build_production.ps1 web` | Publica `https://app.gestinem.es` |
| Preparar Google Play | `bash tool/build_production.sh android` | `.\tool\build_production.ps1 android` | Genera el AAB firmado |
| Preparar APK manual | `bash tool/build_production.sh apk` | `.\tool\build_production.ps1 apk` | Genera el APK firmado |
| Publicar instalador Windows | `bash tool/build_production.sh windows` | `.\tool\build_production.ps1 windows` | Genera y copia el instalador compartido |
| Preparar App Store | `bash tool/build_production.sh ios` | `.\tool\build_production.ps1 ios` | Genera el IPA en un Mac |
| Preparar macOS | `bash tool/build_production.sh macos` | `.\tool\build_production.ps1 macos` | Genera la aplicación en un Mac |

Para desarrollar o revisar la interfaz web no publiques: abre el proyecto en
Flutter, selecciona Chrome y pulsa F5. El comando `web` de esta guía siempre
publica una versión de producción.

## PowerShell y Bash son equivalentes

Hay dos ficheros porque PowerShell y Bash tienen sintaxis distinta, pero ofrecen
los mismos comandos y comprobaciones:

- PowerShell: `tool/build_production.ps1`
- Bash, Warp, Git Bash o macOS: `tool/build_production.sh`

El script Bash no llama internamente a PowerShell. En Warp sobre Windows utiliza
Git Bash/MSYS, por lo que puede ejecutarse directamente con `bash`.

## Antes de generar una versión

Desde la raíz del repositorio:

```bash
git switch main
git pull
cd gestinem_app
git status
```

`git status` debe estar limpio. Los scripts se detienen si hay cambios sin
guardar o si la rama no es `main`.

La versión se cambia únicamente en `pubspec.yaml`:

```yaml
version: 0.1.25+40
```

- Antes del `+` está la versión visible.
- Después del `+` está el número de compilación.
- Google Play exige que cada nuevo número de compilación sea superior al anterior.

Después de cambiarla, crea el commit correspondiente. El script no permite
publicar con ese cambio todavía sin guardar.

## Comprobaciones automáticas

Todos los comandos ejecutan primero:

1. comprobación de rama y estado de Git;
2. `flutter pub get`;
3. `flutter analyze`;
4. `flutter test`;
5. compilación release con el backend de producción;
6. comprobación de que el artefacto esperado existe.

El backend predeterminado es
`https://gest2a3eco-production.up.railway.app`; no hace falta escribirlo en cada
publicación.

## Web: publicar app.gestinem.es

### Preparación del equipo, solo la primera vez

```bash
npm install -g firebase-tools
firebase login
firebase projects:list
railway login
railway status
```

Firebase debe mostrar el proyecto `gest2a3eco` y Railway debe estar vinculado al
proyecto `Gest2A3Eco · Servicios Online`, entorno `production`, servicio
`Gest2A3Eco`. No ejecutes `firebase init`: el repositorio ya contiene la
configuración correcta.

### Publicar desde Bash / Warp

```bash
bash tool/build_production.sh web
```

### Publicar desde PowerShell

```powershell
.\tool\build_production.ps1 web
```

El comando realiza todo el proceso:

1. obtiene de Railway `MESSAGING_VAPID_PUBLIC_KEY` sin mostrar el resto de variables;
2. compila Flutter Web con esa clave pública;
3. configura el service worker dentro de `build/web`;
4. comprueba que no quedan valores pendientes y que VAPID está en el build;
5. publica Firebase Hosting;
6. confirma `https://app.gestinem.es`.

La clave VAPID pública debe formar parte de la aplicación web. Las credenciales
Firebase Admin y cualquier clave privada permanecen exclusivamente en Railway.

No existe otro script de despliegue Firebase ni un comando separado de
“compilar sin publicar”. Para revisar durante el desarrollo usa F5 con Chrome.
La integración continua sí puede compilar sin publicar para verificar el código.

## Android: Google Play

El equipo debe tener `android/key.properties` y el `.jks` privado de carga. No se
suben a Git.

Bash / Warp:

```bash
bash tool/build_production.sh android
```

PowerShell:

```powershell
.\tool\build_production.ps1 android
```

Resultado:
`build/app/outputs/bundle/release/app-release.aab`.

El script no puede completar la publicación en Google Play Console: al terminar,
sube ese AAB a la versión correspondiente de Play Console.

Para una instalación manual fuera de Google Play usa `apk`:

```bash
bash tool/build_production.sh apk
```

```powershell
.\tool\build_production.ps1 apk
```

Resultado: `build/app/outputs/flutter-apk/app-release.apk`.

## Windows: instalador compartido

Debe ejecutarse desde Windows y requiere Flutter para Windows, Visual Studio o
Build Tools e Inno Setup 6.

Bash / Warp:

```bash
bash tool/build_production.sh windows
```

PowerShell:

```powershell
.\tool\build_production.ps1 windows
```

El comando:

1. compila la aplicación Windows release;
2. genera `dist_installer/Gestinem-Windows-<versión>.exe`;
3. verifica el instalador;
4. lo copia de forma segura a
   `\\GestinemMain\Doc_Compartidos\Gest2A3Eco`;
5. compara el SHA-256 del original y de la copia.

Si Inno Setup o la carpeta compartida no están disponibles, el comando termina
con error y explica qué falta. No comunica éxito dejando únicamente el EXE suelto.

## iPhone y iPad

Solo se puede generar desde macOS con Xcode. Antes del primer envío abre
`ios/Runner.xcworkspace` y comprueba en `Signing & Capabilities` el Team y el
identificador `es.gestinem.app`.

Bash:

```bash
bash tool/build_production.sh ios
```

PowerShell 7 en macOS:

```powershell
.\tool\build_production.ps1 ios
```

El IPA queda en `build/ios/ipa/`. Después se sube a App Store Connect mediante
Transporter o Xcode.

## macOS

Bash:

```bash
bash tool/build_production.sh macos
```

PowerShell 7 en macOS:

```powershell
.\tool\build_production.ps1 macos
```

La aplicación queda en `build/macos/Build/Products/Release/`. Para distribuirla
fuera de los equipos de prueba todavía son necesarias la firma Developer ID, la
notarización y el empaquetado DMG o PKG.

## Opciones avanzadas

Estas opciones son equivalentes entre terminales, aunque su sintaxis cambia.

### Cambiar temporalmente el backend

```bash
API_BASE_URL=https://api.gestinem.es bash tool/build_production.sh web
```

```powershell
.\tool\build_production.ps1 web -ApiBaseUrl https://api.gestinem.es
```

### Proporcionar VAPID manualmente

Normalmente no es necesario porque se obtiene de Railway.

```bash
FIREBASE_WEB_VAPID_KEY='<clave-publica>' bash tool/build_production.sh web
```

```powershell
.\tool\build_production.ps1 web -VapidKey '<clave-publica>'
```

### Cambiar la carpeta compartida de Windows

```bash
SHARED_INSTALLER_DIRECTORY='//servidor/carpeta' bash tool/build_production.sh windows
```

```powershell
.\tool\build_production.ps1 windows -SharedInstallerDirectory '\\servidor\carpeta'
```

### Diagnóstico excepcional

Omitir pruebas:

```bash
SKIP_CHECKS=1 bash tool/build_production.sh android
```

```powershell
.\tool\build_production.ps1 android -SkipChecks
```

Permitir otra rama:

```bash
ALLOW_NON_MAIN=1 bash tool/build_production.sh android
```

```powershell
.\tool\build_production.ps1 android -AllowNonMain
```

No uses estas excepciones para una publicación definitiva.

## Errores habituales

- **Hay cambios sin guardar**: crea el commit de la versión y vuelve a ejecutar.
- **Firebase no está autenticado**: ejecuta `firebase login`.
- **Railway no está vinculado**: ejecuta `railway login`, `railway link` y
  `railway status` desde el repositorio.
- **Falta VAPID**: comprueba `MESSAGING_VAPID_PUBLIC_KEY` en el servicio Railway.
- **Bash no encuentra Flutter o Firebase**: cierra y vuelve a abrir Warp después
  de instalarlos para actualizar `PATH`.
- **Falta `android/key.properties`**: restaura la configuración privada de firma.
- **Falta Inno Setup**: instala Inno Setup 6 en Windows.
- **No se accede a Documentos compartidos**: comprueba la conexión con
  `\\GestinemMain\Doc_Compartidos\Gest2A3Eco`.

## Checklist final

- Rama `main` actualizada y árbol Git limpio.
- Versión y número de compilación incrementados en `pubspec.yaml`.
- El script terminó con un mensaje `OK`.
- Web: abre `https://app.gestinem.es` y fuerza una actualización si el navegador
  conserva caché antigua.
- Android: sube el AAB, no el APK, a Google Play.
- Windows: comprueba que el instalador aparece en Documentos compartidos.
- iOS: sube el IPA a App Store Connect.
- Nunca subas `.jks`, `key.properties`, credenciales Firebase Admin ni claves
  privadas a Git.
