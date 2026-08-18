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

## Dominio app.gestinem.es

1. En Railway, abrir el servicio FastAPI y elegir **Settings > Networking >
   Public Networking > Custom Domain**.
2. Introducir `app.gestinem.es` y seleccionar el mismo puerto del dominio
   `gest2a3eco-production.up.railway.app`.
3. Railway mostrara un destino CNAME y un registro TXT de verificacion.
4. En la zona DNS de Raiola, crear ambos registros exactamente como los entrega
   Railway. En RaiolaCP, los nombres completos de registro terminan en punto.
5. Esperar a que Railway marque el dominio como verificado y emita el certificado.
6. Actualizar en Railway:
   - `DGT_PUBLIC_BASE_URL=https://app.gestinem.es`
   - `MESSAGING_PUBLIC_BASE_URL=https://app.gestinem.es`
7. En Microsoft Entra, anadir como URI de redireccion web:
   `https://app.gestinem.es/api/v1/messaging/staff-auth/callback`.
8. Mantener temporalmente tambien la URI de Railway hasta que todos los clientes
   Flutter se hayan actualizado.
9. Recompilar Flutter con `API_BASE_URL=https://app.gestinem.es`.

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
