# Arquitectura de Gestinem Flutter

> **Estado:** Gestinem es una aplicacion Flutter para web, Android, iOS y
> Windows. FastAPI proporciona API, autenticacion, WebSocket, FCM,
> almacenamiento y operaciones internas.

## Alcance y productos

El repositorio contiene cuatro piezas desplegables de forma independiente:

1. Gest2A3Eco Desktop (Python/Tkinter).
2. Backend FastAPI con PostgreSQL.
3. Workers Synology para correo, adjuntos y datos maestros.
4. Gestinem (`gestinem_app/`), aplicacion Flutter web y nativa.

Flutter no importa Python, no accede directamente a PostgreSQL ni al NAS y no
contiene claves internas. Consume FastAPI por HTTPS y WebSocket por WSS. La
version web se publica en Firebase Hosting bajo `https://app.gestinem.es`.

## Estructura Flutter

`lib/app` contiene tema y rutas; `lib/core` concentra configuracion, Dio,
almacenamiento seguro, Firebase y WebSocket; `lib/features` separa `data`,
`domain` y `presentation` para autenticacion, mensajeria, grupos, campanas,
documentos, facturacion y perfil. Riverpod gestiona estado e inyeccion,
`go_router` la navegacion y Dio las peticiones REST.

## Autenticacion

Los clientes usan `POST /api/v1/messaging/auth/login`. El token opaco se guarda
en el almacenamiento seguro disponible para cada plataforma; un 401 elimina la
sesion local y devuelve al acceso.

El personal usa Microsoft Entra. En aplicaciones nativas, el callback entrega
un codigo de un solo uso mediante `es.gestinem.app://auth/callback`. En Flutter
Web, `MESSAGING_APP_WEB_REDIRECT_URI` devuelve el codigo a la ruta HTTPS
configurada. El codigo es valido durante dos minutos y se canjea con
`POST /staff-auth/mobile/exchange`; el token de sesion nunca viaja en la URL.

`WorkstationToken`, `X-Device-Token` y `BACKEND_INTERNAL_API_KEY` son exclusivos
del escritorio y de las integraciones; nunca se distribuyen en Flutter.

## Endpoints principales

- Autenticacion de clientes: `/auth/login`, `/auth/logout`,
  `/auth/forgot-password`, `/auth/reset-password` y `/auth/accept-invite`.
- Autenticacion del despacho: `/staff-auth/login`, `/staff-auth/callback` y
  `/staff-auth/mobile/exchange`.
- Conversaciones: `/client/conversations` y `/staff/conversations`.
- Historial, envio y lectura: `/{audience}/conversations/{id}/messages|read`.
- Adjuntos: `/client/attachments/{id}` y `/staff/attachments/{id}/download`.
- Perfil: `/staff/me`, `/staff/avatar` y `/client/company-profile`.
- Clientes e invitaciones: `/staff/admin/organizations` y
  `/staff/admin/invitations`; el envio masivo usa
  `/staff/admin/invitations/batch`.
- Grupos y campanas: `/staff/groups`, `/staff/admin/groups` y
  `/staff/admin/campaigns`.
- Dispositivos FCM: `/{audience}/app-devices`.
- Tiempo real: `/{audience}/ws-ticket` y
  `/api/v1/messaging/ws/{audience}?ticket=...`.

## Tiempo real y notificaciones

REST es siempre la fuente de verdad. WebSocket avisa de `message.created`,
`message.deleted`, `message.read`, `conversation.updated` y `group.updated`.
Flutter refresca mediante REST y reconecta con espera exponencial de 1 a 30
segundos. El bearer de sesion no viaja en la URL: REST emite un ticket de un
solo uso con 60 segundos de validez.

Las notificaciones usan Firebase Cloud Messaging. Los tokens se guardan en
`msg_app_devices`; una presencia activa evita avisos redundantes. En navegador,
la compilacion web recibe la clave publica de Firebase y publica
`web/firebase-messaging-sw.js` exclusivamente para la recepcion de avisos.

## Invitaciones y correos

- El correo de invitacion enlaza a
  `https://app.gestinem.es/#/accept-invite?token=...`, por lo que el cliente
  puede activar su cuenta y usar Gestinem directamente desde el navegador.
- La respuesta de la API conserva tambien el deep link nativo
  `es.gestinem.app://auth/invite?token=...` para las versiones de tienda.
- Cada invitacion adjunta `Manual_Mensajeria_Gestinem.pdf` y explica que las
  aplicaciones Android y Apple estan en fase de publicacion y todavia no estan
  disponibles en sus tiendas. La plantilla aprobada del comunicado es la
  version 1 (`INVITATION_EMAIL_VERSION = 1`).
- La version 1 explica la privacidad del canal, la atencion compartida de las
  solicitudes generales, la evolucion prevista de los servicios y los canales
  validos desde el 1 de octubre de 2026.
- La recuperacion de contrasena abre la ruta web equivalente y conserva su deep
  link nativo.
- Los avisos de mensaje no incluyen contenido confidencial.

## Configuracion del backend

- `MESSAGING_APP_WEB_URL=https://app.gestinem.es`
- `MESSAGING_APP_REDIRECT_URI=es.gestinem.app://auth/callback`
- `MESSAGING_APP_WEB_REDIRECT_URI=https://app.gestinem.es/#/auth/callback`
- `MESSAGING_FIREBASE_CREDENTIALS` o
  `MESSAGING_FIREBASE_CREDENTIALS_JSON` para Firebase Admin.
- `MESSAGING_CORS_ORIGINS` debe incluir los origenes de Firebase Hosting y el
  dominio personalizado, sin barra final.

## Despliegue

El backend se construye con `backend/Dockerfile`. La imagen incluye el manual
PDF que se adjunta a las invitaciones. Flutter Web se compila y despliega con
`gestinem_app/tool/deploy_firebase.ps1`; FastAPI y PostgreSQL permanecen en
Railway.

Los adjuntos se almacenan temporalmente en Azure Blob. El worker Synology los
reclama, verifica SHA-256, copia al repositorio documental compartido y confirma
la entrega; solo entonces se elimina la copia temporal.
