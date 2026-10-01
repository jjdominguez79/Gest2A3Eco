# Firebase Hosting y notificaciones web

La web de Gestinem se publica en Firebase Hosting y utiliza el backend FastAPI
de Railway. La guía operativa completa está en
[`../docs/flutter_production_build.md`](../docs/flutter_production_build.md).

## Comando único de publicación

Desde `gestinem_app`, en Bash o Warp:

```bash
bash tool/build_production.sh web
```

En PowerShell:

```powershell
.\tool\build_production.ps1 web
```

Ambos comandos hacen lo mismo: pruebas, build release, configuración FCM,
validación y publicación en `https://app.gestinem.es`. No hay que ejecutar un
segundo script de Firebase ni compilar la web manualmente.

Para revisar cambios durante el desarrollo selecciona Chrome en Flutter y pulsa
F5. Eso no modifica la web pública.

## Preparación inicial del equipo

```bash
npm install -g firebase-tools
firebase login
firebase projects:list
railway login
railway status
```

Firebase debe mostrar `gest2a3eco`. Railway debe estar vinculado al proyecto de
producción y al servicio `Gest2A3Eco`. No ejecutes `firebase init`, porque
`firebase.json` y `.firebaserc` ya están configurados.

## VAPID y Firebase Cloud Messaging

El script obtiene automáticamente de Railway la variable
`MESSAGING_VAPID_PUBLIC_KEY` y la incorpora al build Flutter. También completa
la configuración pública de `firebase-messaging-sw.js` a partir de
`lib/firebase_options.dart`.

Antes de publicar comprueba que:

- la clave VAPID está presente en el JavaScript compilado;
- el service worker no conserva marcadores `PENDIENTE_FIREBASE_*`;
- Firebase CLI está autenticado.

La clave VAPID pública no es un secreto y necesariamente llega al navegador. En
cambio, `MESSAGING_FIREBASE_CREDENTIALS_JSON`, claves privadas y credenciales
de proveedores permanecen en Railway y nunca se incluyen en Flutter.

## Separación de responsabilidades

- Firebase Hosting sirve los archivos estáticos de Flutter.
- Firebase Cloud Messaging entrega las notificaciones push.
- Railway ejecuta FastAPI, registra tokens y envía notificaciones mediante
  Firebase Admin.
- `MESSAGING_CORS_ORIGINS` debe autorizar `https://app.gestinem.es`,
  `https://gest2a3eco.web.app` y `https://gest2a3eco.firebaseapp.com` mientras
  estos dos últimos dominios continúen en uso.

El dominio público es `https://app.gestinem.es`; los dominios `web.app` y
`firebaseapp.com` son direcciones técnicas del mismo Hosting.
