# Gestinem

Aplicación Flutter multiplataforma de Gestinem. La versión actual se define exclusivamente en `pubspec.yaml` (actualmente `0.1.3+15`); no dupliques manualmente la versión en otros ficheros.

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

## Builds de producción automatizados

La forma recomendada de compilar es usar los scripts de `tool/`. Ambos usan por defecto el backend de producción y ejecutan `flutter pub get`, `flutter analyze` y `flutter test` antes del build.

### Bash / Warp / macOS / Git Bash

```bash
bash tool/build_production.sh android
bash tool/build_production.sh apk
bash tool/build_production.sh web
bash tool/build_production.sh web-deploy
bash tool/build_production.sh windows
bash tool/build_production.sh ios
bash tool/build_production.sh macos
bash tool/build_production.sh all
```

### PowerShell

```powershell
.\tool\build_production.ps1 android
.\tool\build_production.ps1 apk
.\tool\build_production.ps1 web
.\tool\build_production.ps1 web-deploy
.\tool\build_production.ps1 windows
.\tool\build_production.ps1 ios
.\tool\build_production.ps1 macos
.\tool\build_production.ps1 all
```

Los scripts bloquean por defecto un build si no estás en `main` o si existen cambios sin guardar. Consulta `../docs/flutter_production_build.md` para la guía paso a paso y las opciones avanzadas.

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

Compilar sin publicar:

```bash
bash tool/build_production.sh web
```

Compilar y publicar:

```bash
bash tool/build_production.sh web-deploy
```

En PowerShell pueden usarse los equivalentes de `build_production.ps1` o el script específico `tool/deploy_firebase.ps1`. No ejecutes `firebase init hosting`: `firebase.json` y `.firebaserc` ya están configurados.

## Windows

Desde Windows, tanto Warp/Git Bash como PowerShell están soportados:

```bash
bash tool/build_production.sh windows
```

```powershell
.\tool\build_production.ps1 windows
```

El script compila Flutter release y, si encuentra Inno Setup 6, genera el instalador en `../dist_installer/`. `windows/installer/gestinem.iss` lee automáticamente la versión del ejecutable generado, evitando mantener una versión duplicada.

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

FCM se usa en Android. El backend usa por separado una cuenta de servicio privada mediante `MESSAGING_FIREBASE_CREDENTIALS` o `MESSAGING_FIREBASE_CREDENTIALS_JSON`; ese JSON nunca se incluye en Flutter.

En Windows, REST y WebSocket funcionan con la aplicación abierta, pero Firebase Messaging no ofrece push de producción. El instalador registra el protocolo `es.gestinem.app://` necesario para acceso Microsoft y enlaces seguros.

Más información:

- `../docs/flutter_production_build.md`: procedimiento completo de publicación.
- `FIREBASE_HOSTING.md`: Firebase Hosting.
- `../docs/flutter_messaging_architecture.md`: arquitectura y contrato backend.
