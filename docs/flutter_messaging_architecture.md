# Arquitectura de Gestinem Flutter Messaging

## Alcance y productos

El repositorio contiene tres productos desplegables de forma independiente:

1. Gest2A3Eco Desktop (Python/Tkinter).
2. Backend FastAPI con PostgreSQL y el proceso `messaging-sync`.
3. Gestinem (`gestinem_app/`), una aplicacion Flutter nativa y web.

Flutter no importa Python, no accede a PostgreSQL ni al NAS y no contiene
claves internas. Solo consume FastAPI por HTTPS y WebSocket por WSS. La PWA
anterior permanece intacta y sigue usando los mismos endpoints, SSE y Web Push.

## Estructura Flutter

`lib/app` contiene tema y rutas; `lib/core` concentra configuracion, Dio,
almacenamiento seguro, Firebase y WebSocket; `lib/features` separa `data`,
`domain` y `presentation` para autenticacion, mensajeria, grupos, campanas y
perfil. Riverpod gestiona estado e inyeccion, `go_router` la navegacion y Dio
las peticiones REST.

## Autenticacion

Los clientes usan `POST /api/v1/messaging/auth/login`. El token opaco existente
se guarda con `flutter_secure_storage`; un 401 elimina la sesion local y devuelve
al login. En web, la proteccion efectiva depende del almacenamiento seguro que
ofrezca el navegador.

El personal usa Microsoft Entra. Flutter abre
`GET /staff-auth/login?app=true`; el callback backend crea un codigo de un solo
uso, valido dos minutos, y vuelve a `es.gestinem.app://auth/callback`. La app
canjea el codigo en `POST /staff-auth/mobile/exchange`. El token de sesion no se
incluye en el deep link. Los roles `admin` y `empleado` y los canales proceden
del backend existente.

`workstation_token`, `X-Device-Token` y `DGT_INTERNAL_API_KEY` son exclusivos
del escritorio/integraciones y nunca se distribuyen en Flutter.

## Endpoints principales

- Conversaciones: `GET /client|staff/conversations`.
- Historial/envio/lectura: `/{audience}/conversations/{id}/messages|read`.
- Adjuntos: `/client/attachments/{id}` y `/staff/attachments/{id}/download`.
- Perfil: `/staff/me` (el perfil cliente viene del login existente).
- Internos: `/staff/internal/threads` y sus mensajes.
- Grupos: `/staff/groups` y `/staff/admin/groups`.
- Campanas: `/staff/admin/campaigns` y destinatarios/reintento.
- Dispositivos: `/{audience}/app-devices`.
- Tiempo real: `POST /{audience}/ws-ticket` y `/ws/{audience}?ticket=...`.

Las respuestas añaden `reply_to`, `deleted` y metadatos de borrado sin retirar
campos previos. La PWA no necesita modificarse para ignorarlos.

## Tiempo real

REST es siempre la fuente de verdad. WebSocket avisa de `message.created`,
`message.deleted`, `message.read`, `conversation.updated` y `group.updated`.
Flutter refresca mediante REST al recibirlos y reconecta con backoff exponencial
de 1 a 30 segundos. Una caida WebSocket no bloquea historial ni envio.
El bearer de sesion nunca viaja en la URL: REST emite un ticket de un solo uso
con 60 segundos de validez para cada conexion o reconexion.

Produccion arranca el backend mediante el `CMD` de `backend/Dockerfile`:
`exec uvicorn backend.api.app:app --host 0.0.0.0 --port ${PORT:-8000}
--proxy-headers`. Al no indicar `--workers`, Uvicorn utiliza un unico worker.
El bus actual en memoria requiere ese unico proceso FastAPI. Si se habilitan
varios workers o replicas, debe sustituirse por pub/sub compartido (por ejemplo,
Redis o PostgreSQL) manteniendo el mismo contrato. SSE se conserva para la PWA.

## Respuestas y eliminacion

`reply_to_message_id` es una FK autorreferenciada con `ON DELETE SET NULL` tanto
en mensajes cliente/despacho como internos. La serializacion solo expone id,
autor y un fragmento.

El soft delete conserva fila y auditoria pero oculta cuerpo y adjuntos. El autor
puede borrar su mensaje; solo un administrador puede borrar mensajes ajenos. El
hard delete administrativo borra almacenamiento, adjuntos por cascada y mensaje,
pero conserva `msg_deletion_audit` con actor, motivo y numero de adjuntos.

## Grupos y campanas

`staff_chat` crea un thread interno y autoriza solo administradores/miembros.
`client_list` solo selecciona destinatarios; nunca crea un chat entre clientes.

Una campana materializa destinatarios individuales. Cada mensaje usa
`campaign:{campaign_id}:client:{client_id}` como clave idempotente. El trabajo se
ejecuta despues de responder HTTP mediante `BackgroundTasks`, registra error por
destinatario y admite reintento. Esta interfaz esta encapsulada para migrarla a
una cola persistente en una segunda fase. El reintento selecciona solo
destinatarios `pending` o `error`; la clave idempotente evita duplicar mensajes
si una ejecucion se interrumpio despues de crearlos.

En esta primera fase las campanas son exclusivamente inmediatas. La API rechaza
con HTTP 422 un `scheduled_at` futuro, y Flutter no muestra controles de
programacion. Las campanas programadas y su scheduler persistente quedan para
una segunda fase.

## Firebase Cloud Messaging

El backend lee exclusivamente la ruta
`MESSAGING_FIREBASE_CREDENTIALS`; el JSON no se versiona. Los tokens se guardan
en `msg_app_devices`. Una presencia de dispositivo con conversacion activa evita
notificaciones redundantes. Android queda integrado a nivel de codigo; hay que
aportar el proyecto Firebase y `google-services.json`. iOS/macOS requieren
tambien APNs y `GoogleService-Info.plist`. Web Push/VAPID de la PWA se conserva.

## Configuracion backend

- `MESSAGING_APP_REDIRECT_URI=es.gestinem.app://auth/callback`
- `MESSAGING_APP_WEB_REDIRECT_URI=https://app.example.com/auth/callback`
- `MESSAGING_FIREBASE_CREDENTIALS=C:\ruta\privada\firebase-service-account.json`
- Variables existentes de Entra, VAPID, almacenamiento y PostgreSQL.

Aplicar `backend/migrations/002_flutter_messaging.sql` antes del despliegue. El
startup tambien añade de forma compatible las columnas autorreferenciadas para
instalaciones que usan el mecanismo historico de migracion aditiva.

## Configuracion y despliegue Flutter

Los entornos usan `--dart-define`: `API_BASE_URL`, `WEBSOCKET_URL` opcional y
`ENVIRONMENT=development|production`. No hay URL en widgets. Consultar
`gestinem_app/README.md` para Android, Windows, iOS, macOS y web.

## Estrategia de migracion

1. Desplegar migracion y backend compatible.
2. Configurar deep link y Firebase en un entorno de pruebas.
3. Publicar Gestinem por plataforma sin tocar Gest2A3Eco Desktop.
4. Mantener PWA/SSE/Web Push durante adopcion y comparar trazabilidad.
5. En una fase posterior, implantar scheduler y cola persistentes, pub/sub
   multi-worker y decidir la retirada de la PWA con datos reales de uso.
