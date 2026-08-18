# Arquitectura de Gestinem Flutter Messaging

> **Estado:** PWA heredada retirada el 2026-08-18. Flutter es el unico cliente
> de interfaz de mensajeria. FastAPI solo proporciona API, autenticacion,
> WebSocket, FCM, almacenamiento y operaciones internas.

## Alcance y productos

El repositorio contiene tres productos desplegables de forma independiente:

1. Gest2A3Eco Desktop (Python/Tkinter).
2. Backend FastAPI con PostgreSQL y el proceso `messaging-sync`.
3. Gestinem (`gestinem_app/`), una aplicacion Flutter nativa (iOS/Android/Windows).

Flutter no importa Python, no accede a PostgreSQL ni al NAS y no contiene
claves internas. Solo consume FastAPI por HTTPS y WebSocket por WSS.

**La PWA anterior (`/mensajes`, `/equipo/mensajes`) ha sido retirada.**
Los adjuntos de mensajeria proceden del cliente Flutter, no de ninguna PWA.
La aplicacion de escritorio ya no abre ninguna URL de mensajeria web.

## Estructura Flutter

`lib/app` contiene tema y rutas; `lib/core` concentra configuracion, Dio,
almacenamiento seguro, Firebase y WebSocket; `lib/features` separa `data`,
`domain` y `presentation` para autenticacion, mensajeria, grupos, campanas y
perfil. Riverpod gestiona estado e inyeccion, `go_router` la navegacion y Dio
las peticiones REST.

## Autenticacion

Los clientes usan `POST /api/v1/messaging/auth/login`. El token opaco existente
se guarda con `flutter_secure_storage`; un 401 elimina la sesion local y devuelve
al login.

El personal usa Microsoft Entra. Flutter abre
`GET /staff-auth/login?app=true`; el callback backend crea un codigo de un solo
uso, valido dos minutos, y vuelve a `es.gestinem.app://auth/callback`. La app
canjea el codigo en `POST /staff-auth/mobile/exchange`. El token de sesion no se
incluye en el deep link. El parametro `app=true` es **obligatorio**: el flujo web
(sin `app=true`) ya no tiene destino valido y retorna 410.

`workstation_token`, `X-Device-Token` y `DGT_INTERNAL_API_KEY` son exclusivos
del escritorio/integraciones y nunca se distribuyen en Flutter.

## Endpoints principales (contratos conservados para Flutter)

- Autenticacion clientes: `POST /auth/login`, `POST /auth/logout`, `POST /auth/forgot-password`, `POST /auth/reset-password`.
- Autenticacion despacho: `GET /staff-auth/login?app=true`, `GET /staff-auth/callback`, `POST /staff-auth/mobile/exchange`.
- Conversaciones: `GET /client|staff/conversations`.
- Historial/envio/lectura: `/{audience}/conversations/{id}/messages|read`.
- Adjuntos: `/client/attachments/{id}` y `/staff/attachments/{id}/download`.
- Perfil: `/staff/me`, `/staff/avatar`.
- Internos: `/staff/internal/threads` y sus mensajes.
- Grupos: `/staff/groups` y `/staff/admin/groups`.
- Campanas: `/staff/admin/campaigns` y destinatarios/reintento.
- Dispositivos FCM: `/{audience}/app-devices`.
- Tiempo real: `POST /{audience}/ws-ticket` y `/api/v1/messaging/ws/{audience}?ticket=...`.
- WebSocket: `/api/v1/messaging/ws/{audience}`.

### Endpoints retirados (PWA)
- `/mensajes` → 410 Gone
- `/equipo/mensajes` → 410 Gone
- `/staff/push/config`, `/staff/push/subscriptions`, `/staff/push/test` → 404
- `/client/push/config`, `/client/push/subscriptions`, `/client/push/test` → 404

## Tiempo real

REST es siempre la fuente de verdad. WebSocket avisa de `message.created`,
`message.deleted`, `message.read`, `conversation.updated` y `group.updated`.
Flutter refresca mediante REST al recibirlos y reconecta con backoff exponencial
de 1 a 30 segundos. Una caida WebSocket no bloquea historial ni envio.
El bearer de sesion nunca viaja en la URL: REST emite un ticket de un solo uso
con 60 segundos de validez para cada conexion o reconexion.

SSE (`services/mensajeria_service.py`) se conserva exclusivamente para la
aplicacion de escritorio, que lo usa para notificaciones nativas. No es una
funcion de la PWA.

## Notificaciones push

**FCM (Firebase Cloud Messaging)** es el unico sistema de notificaciones push.
Web Push/VAPID ha sido eliminado:
- `pywebpush` removido de `backend/requirements.txt`.
- `MESSAGING_VAPID_PUBLIC_KEY`, `MESSAGING_VAPID_PRIVATE_KEY`, `MESSAGING_VAPID_SUBJECT` eliminados de `config.py`.
- Tablas `msg_push_subscriptions` y `msg_client_push_subscriptions` eliminadas (ver migracion 004).

Los tokens FCM se guardan en `msg_app_devices`. Una presencia de dispositivo con
conversacion activa evita notificaciones redundantes.

## Invitaciones y correos

- Las invitaciones usan `es.gestinem.app://auth/invite?token=...`; Flutter permite
  crear la contrasena y abre la sesion del cliente.
- La recuperacion usa `es.gestinem.app://auth/reset?token=...`; Flutter permite
  establecer una contrasena nueva.
- El aviso de nuevo mensaje se envia sin enlace y pide abrir la aplicacion.

## Service workers de retirada (TRANSITORIOS)

Los endpoints `/mensajes-sw.js` y `/equipo/mensajes-sw.js` sirven un script
minimo que desinstala los service workers ya instalados en los navegadores de
usuarios que tuvieran la PWA guardada. **Deben eliminarse 60 dias despues del
despliegue de esta version** (aproximadamente 2026-10-18).

## Configuracion backend

- `MESSAGING_APP_REDIRECT_URI=es.gestinem.app://auth/callback`
- `MESSAGING_APP_WEB_REDIRECT_URI=https://app.example.com/auth/callback`
- `MESSAGING_FIREBASE_CREDENTIALS=C:\ruta\privada\firebase-service-account.json`
- En Railway, `MESSAGING_FIREBASE_CREDENTIALS_JSON` puede contener el JSON
  completo como variable secreta en lugar de una ruta de fichero.
- Variables de Entra, almacenamiento Azure/local y PostgreSQL.

**Variables eliminadas:** `MESSAGING_VAPID_PUBLIC_KEY`, `MESSAGING_VAPID_PRIVATE_KEY`,
`MESSAGING_VAPID_SUBJECT`.

Aplicar migraciones `002_flutter_messaging.sql`, `003_ux_iteration.sql` y
`004_remove_web_push.sql` antes del despliegue.

## Configuracion y despliegue Flutter

Los entornos usan `--dart-define`: `API_BASE_URL`, `WEBSOCKET_URL` opcional y
`ENVIRONMENT=development|production`. No hay URL en widgets. Consultar
`gestinem_app/README.md` para Android, Windows, iOS y macOS.
