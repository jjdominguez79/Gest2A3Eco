# Gestinem

Aplicación Flutter multiplataforma de Gestinem. La versión actual se define
exclusivamente en `pubspec.yaml`; no la dupliques manualmente en otros ficheros.

## Estado de producción

- Backend FastAPI: `https://gest2a3eco-production.up.railway.app`.
- Web: `https://app.gestinem.es`, publicada en Firebase Hosting.
- Android: `es.gestinem.app`, distribución por Google Play mediante AAB release firmado.
- iOS: `es.gestinem.app`, compilación y distribución desde macOS/Xcode.
- Windows: build release + instalador Inno Setup; la versión del instalador se obtiene automáticamente del EXE.
- macOS: build release disponible; la distribución externa requiere firma/notarización Apple.
- Linux: no está configurado actualmente como plataforma soportada.

## Requisitos

- Flutter estable compatible con Dart 3.11.
- Backend accesible mediante HTTPS.
- Android release: `android/key.properties` y el `.jks` privado correspondiente.
- Web: Firebase CLI autenticado para desplegar Hosting.
- Windows: Visual Studio/Build Tools para Flutter; Inno Setup 6 para generar instalador.
- iOS/macOS: Mac con Xcode. Para distribución Apple, cuenta y firma de Apple Developer.

Las credenciales privadas (`key.properties`, `.jks`, Firebase Admin, etc.) nunca se versionan.

## Desarrollo

```bash
flutter pub get
flutter run --dart-define=API_BASE_URL=https://gest2a3eco-production.up.railway.app --dart-define=ENVIRONMENT=development
flutter analyze
flutter test
```

`API_BASE_URL` es la raíz del backend, sin `/api/v1/messaging`.

## Generar y publicar versiones

La guía operativa única está en
[`../docs/flutter_production_build.md`](../docs/flutter_production_build.md).
Los dos scripts son entradas equivalentes para terminales distintos:

- Bash, Warp, Git Bash y macOS: `tool/build_production.sh`.
- PowerShell: `tool/build_production.ps1`.

Desde `gestinem_app`, elige una plataforma:

| Plataforma | Bash / Warp | PowerShell |
|---|---|---|
| Web, publicación completa | `bash tool/build_production.sh web` | `.\tool\build_production.ps1 web` |
| Android, AAB para Play | `bash tool/build_production.sh android` | `.\tool\build_production.ps1 android` |
| Android, APK manual | `bash tool/build_production.sh apk` | `.\tool\build_production.ps1 apk` |
| Windows, instalador compartido | `bash tool/build_production.sh windows` | `.\tool\build_production.ps1 windows` |
| iOS, IPA | `bash tool/build_production.sh ios` | `.\tool\build_production.ps1 ios` |
| macOS, aplicación | `bash tool/build_production.sh macos` | `.\tool\build_production.ps1 macos` |

No existe un segundo procedimiento para Firebase. El comando `web` obtiene
VAPID de Railway, compila, valida y publica Firebase Hosting. Para desarrollar
o revisar la web selecciona Chrome en Flutter y pulsa F5.

Los scripts exigen `main` y un árbol Git limpio, y ejecutan `flutter pub get`,
`flutter analyze` y `flutter test` antes de producir el artefacto.

## Android

Para Google Play usa siempre AAB release firmado:

```bash
bash tool/build_production.sh android
```

Salida: `build/app/outputs/bundle/release/app-release.aab`.

Para instalación manual:

```bash
bash tool/build_production.sh apk
```

Salida: `build/app/outputs/flutter-apk/app-release.apk`.

El build Gradle release falla deliberadamente si falta la configuración de firma. `google-services.json` se mantiene local en `android/app/` y no se versiona.

## Web / Firebase Hosting

```bash
bash tool/build_production.sh web
```

```powershell
.\tool\build_production.ps1 web
```

Ambos publican `https://app.gestinem.es` con la configuración de notificaciones
web. No ejecutes `firebase init`: `firebase.json` y `.firebaserc` ya están
configurados. Consulta [`FIREBASE_HOSTING.md`](FIREBASE_HOSTING.md) para los
requisitos iniciales de Firebase CLI y Railway CLI.

## Windows

Desde Windows, tanto Warp/Git Bash como PowerShell están soportados:

```bash
bash tool/build_production.sh windows
```

```powershell
.\tool\build_production.ps1 windows
```

El script compila Flutter release, exige Inno Setup 6, genera el instalador en
`../dist_installer/` y copia ese mismo instalador versionado a
`\\GestinemMain\Doc_Compartidos\Gest2A3Eco`, comprobando su SHA-256 antes de
confirmar la publicación. `windows/installer/gestinem.iss` lee automáticamente
la versión del ejecutable generado.

El destino compartido puede cambiarse con el parámetro PowerShell `-SharedInstallerDirectory` o con la variable `SHARED_INSTALLER_DIRECTORY` al usar Bash. Si no se indica, también se respeta `GEST2A3ECO_DOCUMENT_REPOSITORY_DIR` antes de aplicar la ruta predeterminada.

El instalador Windows es para distribución interna y no se adjunta a las
Releases públicas de Gest2A3Eco.

## iOS

Solo desde macOS. Configura primero `Runner` > `Signing & Capabilities` en Xcode con el Team de Apple Developer y verifica el bundle ID `es.gestinem.app`.

```bash
bash tool/build_production.sh ios
```

Se utiliza `flutter build ipa --release`; el resultado se encuentra en `build/ios/ipa/` y es el artefacto para TestFlight/App Store Connect.

## macOS

```bash
bash tool/build_production.sh macos
```

El `.app` queda en `build/macos/Build/Products/Release/`. Para distribución externa hay que completar firma Developer ID, notarización y empaquetado DMG/PKG.

## Firebase y notificaciones

FCM se usa en Android y Web. Durante la publicación web, la clave pública VAPID
se obtiene de `MESSAGING_VAPID_PUBLIC_KEY` en Railway. El backend usa por
separado una cuenta de servicio privada mediante
`MESSAGING_FIREBASE_CREDENTIALS` o `MESSAGING_FIREBASE_CREDENTIALS_JSON`; ese
JSON nunca se incluye en Flutter.

En Windows, REST y WebSocket funcionan con la aplicación abierta, pero Firebase Messaging no ofrece push de producción. El instalador registra el protocolo `es.gestinem.app://` necesario para acceso Microsoft y enlaces seguros.

Más información:

- `../docs/flutter_production_build.md`: procedimiento completo de publicación.
- `FIREBASE_HOSTING.md`: Firebase Hosting.
- `../docs/flutter_messaging_architecture.md`: arquitectura y contrato backend.

## Solicitudes de cambio de datos

Desde `Mi área` el cliente ve por separado su usuario, los datos compartidos de
la empresa y el historial de solicitudes. Desde el logotipo o desde
`Solicitar modificación` puede proponer cambios de su ficha, cuentas bancarias
o identidad corporativa. La aplicación envía una solicitud pendiente y un
aviso al chat privado del despacho; nunca modifica
directamente los datos maestros del escritorio.
