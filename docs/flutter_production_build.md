# Builds y despliegues de producción — Gestinem Flutter

Esta es la guía operativa. Si dudas, sigue los pasos en orden y no improvises parámetros.

## 1. Antes de publicar

Desde la raíz del repositorio:

```bash
git switch main
git pull
git status
cd gestinem_app
```

`git status` debe indicar que no hay cambios pendientes. Los scripts de producción se detienen si detectan otra rama o cambios sin guardar.

## 2. Subir versión

La única fuente de versión es `gestinem_app/pubspec.yaml`:

```yaml
version: 0.1.3+15
```

Para una nueva compilación de la misma versión funcional, incrementa el número posterior a `+`, por ejemplo `0.1.3+16`. Para una nueva versión funcional puedes usar, por ejemplo, `0.1.4+16`.

Google Play exige que cada nuevo `versionCode` (el número después de `+`) sea superior al anterior.

Después del cambio, haz commit y vuelve a comprobar que el árbol está limpio antes del build.

## 3. Qué hace la automatización

Hay dos entradas equivalentes:

- Bash: `tool/build_production.sh`
- PowerShell: `tool/build_production.ps1`

Por defecto:

1. Comprueban la rama `main`.
2. Comprueban que no haya cambios sin guardar.
3. Ejecutan `flutter pub get`.
4. Ejecutan `flutter analyze`.
5. Ejecutan `flutter test`.
6. Compilan con `ENVIRONMENT=production` y `API_BASE_URL=https://gest2a3eco-production.up.railway.app`.

No necesitas escribir la URL de Railway cada vez.

## 4. Android — Google Play

Comprueba que en el equipo existen `android/key.properties` y el `.jks` privado de carga. No se suben a Git.

Bash/Warp:

```bash
bash tool/build_production.sh android
```

PowerShell:

```powershell
.\tool\build_production.ps1 android
```

Sube a Google Play Console únicamente:

`build/app/outputs/bundle/release/app-release.aab`

## 5. Android — APK manual

Bash/Warp:

```bash
bash tool/build_production.sh apk
```

PowerShell:

```powershell
.\tool\build_production.ps1 apk
```

Resultado: `build/app/outputs/flutter-apk/app-release.apk`.

El APK es para instalación manual/pruebas; para Play Store usa AAB.

## 6. Web — comprobar sin publicar

```bash
bash tool/build_production.sh web
```

O:

```powershell
.\tool\build_production.ps1 web
```

Resultado: `build/web/`. No modifica la web pública.

## 7. Web — publicar app.gestinem.es

La primera vez en un equipo:

```bash
npm install -g firebase-tools
firebase login
firebase projects:list
```

Debe aparecer el proyecto `gest2a3eco`. No ejecutes `firebase init`.

Publicar desde Bash/Warp:

```bash
bash tool/build_production.sh web-deploy
```

Publicar desde PowerShell:

```powershell
.\tool\build_production.ps1 web-deploy
```

Después comprueba `https://app.gestinem.es`.

## 8. Windows

Debe hacerse desde Windows. El camino recomendado es PowerShell:

```powershell
.\tool\build_production.ps1 windows
```

Compila `build/windows/x64/runner/Release/` y, si Inno Setup 6 está instalado en la ruta estándar, genera automáticamente el instalador en `../dist_installer/`.

El instalador obtiene la versión del propio `gestinem.exe`; no hay que editar manualmente `gestinem.iss` al cambiar la versión.

Si solo necesitas compilar manualmente desde una terminal Bash de Windows:

```bash
flutter build windows --release --dart-define=API_BASE_URL=https://gest2a3eco-production.up.railway.app --dart-define=ENVIRONMENT=production
```

## 9. iPhone/iPad

Solo desde Mac.

Primera configuración o si cambia la firma:

```bash
open ios/Runner.xcworkspace
```

En Xcode comprueba `Runner` > `Signing & Capabilities`, selecciona el Team correcto y verifica `es.gestinem.app`.

Build:

```bash
bash tool/build_production.sh ios
```

Resultado: `build/ios/ipa/`. Sube el IPA a TestFlight/App Store Connect mediante las herramientas de Apple.

## 10. macOS

Solo desde Mac:

```bash
bash tool/build_production.sh macos
```

Resultado: `build/macos/Build/Products/Release/`.

La compilación local no equivale a una distribución pública. Para entregar la app fuera de los equipos de prueba hay que configurar firma Developer ID, notarización Apple y DMG/PKG.

## 11. Compilar todo lo posible en el equipo

Bash:

```bash
bash tool/build_production.sh all
```

PowerShell:

```powershell
.\tool\build_production.ps1 all
```

`all` no publica Firebase automáticamente: genera los artefactos. La publicación web debe hacerse explícitamente con `web-deploy`.

## 12. Opciones avanzadas

Cambiar temporalmente el backend en Bash:

```bash
API_BASE_URL=https://api.gestinem.es bash tool/build_production.sh web
```

En PowerShell:

```powershell
.\tool\build_production.ps1 web -ApiBaseUrl https://api.gestinem.es
```

Omitir analyze/test (solo para diagnóstico, no recomendado para una publicación real):

```bash
SKIP_CHECKS=1 bash tool/build_production.sh web
```

```powershell
.\tool\build_production.ps1 web -SkipChecks
```

Permitir otra rama de forma consciente:

```bash
ALLOW_NON_MAIN=1 bash tool/build_production.sh web
```

```powershell
.\tool\build_production.ps1 web -AllowNonMain
```

## 13. Checklist final

- Rama `main` actualizada.
- Árbol Git limpio.
- Versión incrementada en `pubspec.yaml` y commit realizado.
- `flutter analyze` correcto.
- `flutter test` correcto.
- Android firmado con la clave de carga correcta.
- Artefacto correcto: AAB para Play, IPA para Apple, instalador para Windows.
- Web comprobada tras el despliegue.
- Nunca subir `.jks`, `key.properties` ni credenciales Firebase Admin a Git.
