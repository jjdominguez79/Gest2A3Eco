# Despliegue piloto de Gestinem Flutter

## Backend inmediato

El piloto usa temporalmente:

`https://gest2a3eco-production.up.railway.app`

La URL se pasa a Flutter mediante `API_BASE_URL`; no se guarda ninguna clave en
la aplicacion.

## Firebase en Railway

1. En Firebase, generar una cuenta de servicio para Firebase Admin.
2. En Railway, crear la variable secreta
   `MESSAGING_FIREBASE_CREDENTIALS_JSON` con el JSON completo en una sola linea.
3. No guardar ese JSON en Git, en Flutter ni en configuracion de escritorio.
4. Desplegar el backend y comprobar que el alta de un dispositivo devuelve
   `fcm_configured: true`.

El fichero Android `google-services.json` es configuracion del cliente y se
ubica localmente en `gestinem_app/android/app/`; permanece excluido de Git.

## Dominios del piloto

- Frontend Flutter Web: `https://app.gestinem.es`, servido por Firebase Hosting.
- Backend FastAPI: `https://gest2a3eco-production.up.railway.app`.

La zona DNS de Raiola contiene:

```text
app.gestinem.es.  CNAME  gest2a3eco.web.app.
```

Railway debe mantener:

```text
DGT_PUBLIC_BASE_URL=https://gest2a3eco-production.up.railway.app
MESSAGING_PUBLIC_BASE_URL=https://gest2a3eco-production.up.railway.app
MESSAGING_APP_WEB_REDIRECT_URI=https://app.gestinem.es/auth/callback
```

En Microsoft Entra, la URI de redireccion del backend sigue siendo:

```text
https://gest2a3eco-production.up.railway.app/api/v1/messaging/staff-auth/callback
```

Cuando exista `api.gestinem.es`, migrar conjuntamente las dos URL publicas de
Railway, la URI de Microsoft Entra y `API_BASE_URL` de todos los clientes.

## Compilaciones del piloto

```powershell
Set-Location gestinem_app

flutter build apk --debug `
  --dart-define=API_BASE_URL=https://gest2a3eco-production.up.railway.app `
  --dart-define=ENVIRONMENT=production

flutter build windows --release `
  --dart-define=API_BASE_URL=https://gest2a3eco-production.up.railway.app `
  --dart-define=ENVIRONMENT=production
```

El APK `debug` solo sirve para el dispositivo piloto. La distribucion general
requiere una clave de carga Android y un App Bundle `release` firmado.
