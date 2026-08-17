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

Ejecutar `flutterfire configure` para generar la configuracion definitiva y
seguir las instrucciones de FlutterFire para activar el plugin de Google
Services. Sin Firebase, REST y WebSocket siguen funcionando.

La arquitectura completa y el contrato backend estan en
[`../docs/flutter_messaging_architecture.md`](../docs/flutter_messaging_architecture.md).
