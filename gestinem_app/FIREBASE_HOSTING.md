# Firebase Hosting para Gestinem Flutter Web

La aplicacion web se publica como contenido estatico en Firebase Hosting. El
backend FastAPI, PostgreSQL y los WebSocket permanecen en Railway.

## Primera configuracion del equipo

Instalar Firebase CLI y autenticar la cuenta que tiene acceso al proyecto
`gest2a3eco`:

```powershell
npm install -g firebase-tools
firebase login
firebase projects:list
```

No ejecutar `firebase init hosting`: los ficheros `firebase.json` y
`.firebaserc` de este directorio ya contienen la configuracion del proyecto. Un
nuevo `firebase init` podria sobrescribirla.

## Compilar y desplegar

Desde `gestinem_app`:

```powershell
.\tool\deploy_firebase.ps1
```

El script compila la version web contra el backend piloto de Railway y publica
solo Firebase Hosting. Para utilizar otro backend:

```powershell
.\tool\deploy_firebase.ps1 -ApiBaseUrl "https://api.gestinem.es"
```

Para validar unicamente la compilacion:

```powershell
.\tool\deploy_firebase.ps1 -BuildOnly
```

Tras el primer despliegue, Firebase mostrara las direcciones:

- `https://gest2a3eco.web.app`
- `https://gest2a3eco.firebaseapp.com`

## Configuracion de Railway

La web se sirve desde un origen diferente al backend. Anadir a
`MESSAGING_CORS_ORIGINS` en Railway todos los origenes autorizados, separados
por comas y sin barra final. Durante el piloto:

```text
https://gest2a3eco.web.app,https://gest2a3eco.firebaseapp.com
```

El origen definitivo `https://app.gestinem.es` tambien debe estar autorizado.
No retirar los dominios predeterminados hasta comprobar que ningun usuario los
utiliza.

## Dominio personalizado

El frontend usa `app.gestinem.es`, asociado al sitio Firebase `gest2a3eco`. En
la zona DNS de Raiola el CNAME es:

```text
app.gestinem.es.  CNAME  gest2a3eco.web.app.
```

El backend permanece en `https://gest2a3eco-production.up.railway.app` hasta
que se configure un dominio API independiente, por ejemplo `api.gestinem.es`.

Firebase emite y renueva automaticamente el certificado TLS. No se guardan
claves privadas ni credenciales de Firebase en este repositorio.

## Notificaciones web

Firebase Hosting y Firebase Cloud Messaging son configuraciones independientes.
Publicar la web no activa por si solo las notificaciones del navegador. Para
ello siguen siendo necesarios la aplicacion web de Firebase, la clave publica
VAPID y `web/firebase-messaging-sw.js`.
