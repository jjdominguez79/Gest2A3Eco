# Gestinem

Aplicacion Flutter independiente para los servicios de Gestinem. En la version
`0.1.0+1` incorpora mensajeria para clientes y personal del despacho.

## Requisitos

- Flutter estable con Dart 3.11 o compatible.
- Backend FastAPI accesible mediante HTTPS.
- Para el acceso del personal, registrar `es.gestinem.app://auth/callback` como
  retorno de la aplicacion.

## Desarrollo

```powershell
flutter pub get
flutter run --dart-define=API_BASE_URL=https://api.example.com --dart-define=ENVIRONMENT=development
flutter test
flutter analyze
```

`API_BASE_URL` es la raiz del backend, sin `/api/v1/messaging`. Si no se define,
en desarrollo se usa `http://localhost:8000`. Se puede sobrescribir el WebSocket:

```powershell
flutter run --dart-define=API_BASE_URL=https://api.example.com `
  --dart-define=WEBSOCKET_URL=wss://realtime.example.com `
  --dart-define=ENVIRONMENT=production
```

Para el login de personal en web, definir tambien
`APP_AUTH_REDIRECT_URI=https://app.example.com/auth/callback` y configurar el
mismo valor en `MESSAGING_APP_WEB_REDIRECT_URI` del backend.

## Compilacion

```powershell
flutter build apk --dart-define=API_BASE_URL=https://api.example.com --dart-define=ENVIRONMENT=production
flutter build windows --dart-define=API_BASE_URL=https://api.example.com --dart-define=ENVIRONMENT=production
flutter build web --dart-define=API_BASE_URL=https://api.example.com --dart-define=ENVIRONMENT=production
```

En macOS:

```bash
flutter build ios --release --dart-define=API_BASE_URL=https://api.example.com --dart-define=ENVIRONMENT=production
flutter build macos --release --dart-define=API_BASE_URL=https://api.example.com --dart-define=ENVIRONMENT=production
```

## Firebase

No se versionan credenciales. Copiar y completar los archivos `.example`:

- Android: `android/app/google-services.json`.
- iOS: `ios/Runner/GoogleService-Info.plist`.

Para Android, registrar en Firebase la aplicacion `es.gestinem.app`, descargar
`google-services.json` y copiarlo a `android/app/`. El plugin de Google Services
se activa automaticamente cuando existe ese archivo. El backend usa, por
separado, una cuenta de servicio privada indicada por
`MESSAGING_FIREBASE_CREDENTIALS` o, en Railway, por la variable secreta
`MESSAGING_FIREBASE_CREDENTIALS_JSON`; ese JSON nunca se incluye en Flutter.

FCM se usa en Android. En Windows, REST y WebSocket funcionan mientras la
aplicacion esta abierta, pero Firebase Messaging no ofrece push de produccion.
Al abrirse en Windows, la aplicacion registra para el usuario actual el protocolo
`es.gestinem.app://`, necesario para el acceso Microsoft y los enlaces seguros.

## Firma Android

La version `release` nunca usa la clave de depuracion. Crear una clave de carga,
copiar `android/key.properties.example` como `android/key.properties` y completar
las cuatro propiedades. Ambos archivos privados estan excluidos de Git.

```powershell
keytool -genkeypair -v -keystore C:\ruta\privada\gestinem-upload.jks `
  -keyalg RSA -keysize 2048 -validity 10000 -alias gestinem
flutter build appbundle --release `
  --dart-define=API_BASE_URL=https://gest2a3eco-production.up.railway.app `
  --dart-define=ENVIRONMENT=production
```

Para el piloto actual en Railway, usar como `API_BASE_URL`:

`https://gest2a3eco-production.up.railway.app`

Cuando `app.gestinem.es` este verificado en Railway, recompilar los clientes con
esa URL. Consultar `../docs/flutter_pilot_deployment.md`.

En Windows, despues del build, generar el instalador interno con Inno Setup 6:

```powershell
& 'C:\Program Files (x86)\Inno Setup 6\ISCC.exe' windows\installer\gestinem.iss
```

El instalador por usuario se crea en `../dist_installer/`, no necesita permisos
de administrador y registra el protocolo seguro de Gestinem. Para uso empresarial
hay que activar una licencia comercial de Inno Setup o sustituir este empaquetado
por MSIX antes de distribuirlo.

La arquitectura completa y el contrato backend estan en
[`../docs/flutter_messaging_architecture.md`](../docs/flutter_messaging_architecture.md).
