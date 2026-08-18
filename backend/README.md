# Backend de integraciones y mensajeria

Backend FastAPI independiente del escritorio. Sirve los tramites DGT, OCR
Azure, SignRequest, Dataprius y los portales de mensajeria de clientes y
empleados. Revisado contra el codigo el 2026-08-15.

## Desarrollo local

```powershell
python -m pip install -r backend/requirements.txt
$env:DGT_DATABASE_URL = "postgresql+psycopg://usuario:password@localhost:5432/gest2a3eco_backend"
$env:DGT_INTERNAL_API_KEY = "secreto-solo-desarrollo"
$env:DGT_PUBLIC_BASE_URL = "http://localhost:8000"
python -m uvicorn backend.api.app:app --reload
```

Comprobaciones:

- `GET /health`
- OpenAPI en `/docs` y `/openapi.json`
- portal DGT en `/t/{referencia}/{rol}`
- PWA de clientes en `/mensajes`
- PWA de empleados en `/equipo/mensajes`

La base del backend es PostgreSQL y se configura exclusivamente mediante
`DGT_DATABASE_URL`. No existe fallback a SQLite. El esquema inicial esta en
`backend/migrations/001_initial.sql`; los modelos aplican las ampliaciones
aditivas posteriores.

## Servicios

- **DGT:** expedientes, partes, vehiculos, enlaces con caducidad, documentos,
  subsanaciones, validacion, firma, auditoria y portal publico por rol.
- **OCR:** `POST /api/v1/ocr/invoices/analyze` delega en Azure Document
  Intelligence sin exponer su clave al escritorio.
- **Firma:** proxy de envio, consulta, cancelacion, reenvio y evidencias de
  SignRequest.
- **Dataprius:** carga de documentos en la ruta solicitada por el escritorio o
  por el flujo DGT.
- **Mensajeria:** invitaciones, autenticacion de clientes, acceso Microsoft 365
  del personal, chats con adjuntos, respuestas, borrado auditado, grupos,
  campanas, FCM y eventos en tiempo real.
- **Cliente movil:** aplicacion Flutter funcional para clientes y empleados,
  con codigos de acceso, registro/presencia de dispositivos y WebSocket.
- **Worker de adjuntos:** endpoints tecnicos para reclamar, descargar, verificar
  y confirmar archivos temporales.

## Autenticacion

La cabecera `X-API-Key` tiene dos credenciales posibles segun la ruta:

- `DGT_INTERNAL_API_KEY`: administracion de puestos y organizaciones,
  invitaciones internas y otras rutas exclusivas del servidor.
- `WorkstationToken`: operaciones del escritorio en DGT, OCR, firma,
  Dataprius, estado de integraciones y alta del dispositivo de mensajeria.

Un `WorkstationToken` no puede acceder a endpoints administrativos. Los portales
web usan sesiones propias y el worker de adjuntos usa `X-Sync-Token` con
`MESSAGING_SYNC_TOKEN`.

En cada puesto se configuran las URLs `integrations_api_url` y
`messaging_api_url`; el token se guarda en Windows Credential Manager, nunca en
el JSON local. En el primer acceso, el escritorio obtiene un token de dispositivo
revocable y tambien lo guarda en Credential Manager.

## Variables de entorno

### Nucleo y DGT

- `DGT_DATABASE_URL`: DSN SQLAlchemy PostgreSQL obligatorio.
- `DGT_INTERNAL_API_KEY`: credencial interna obligatoria fuera de pruebas.
- `DGT_PUBLIC_BASE_URL`: origen de enlaces publicos.
- `DGT_TOKEN_TTL_HOURS`: caducidad de enlaces; 168 horas por defecto.
- `DGT_STORAGE_DIR`: almacenamiento privado local de desarrollo.

### OCR e integraciones

- `AZURE_DOC_INTELLIGENCE_ENDPOINT`, `AZURE_DOC_INTELLIGENCE_KEY` y
  `AZURE_DOC_INTELLIGENCE_MODEL_ID`.
- `AZURE_OCR_TRAINING_CONNECTION_STRING` y
  `AZURE_OCR_TRAINING_CONTAINER` para exportaciones de aprendizaje.
- `SIGNREQUEST_TOKEN`, `SIGNREQUEST_FROM_EMAIL`,
  `SIGNREQUEST_GESTOR_EMAIL`, `SIGNREQUEST_GESTOR_TELEFONO` y
  `SIGNREQUEST_BASE_URL`.
- `DATAPRIUS_API_KEY`, `DATAPRIUS_API_SECRET`, `DATAPRIUS_BASE_URL` y
  `DATAPRIUS_BASE_PATH`.

### Mensajeria

- `MESSAGING_PUBLIC_BASE_URL`: origen HTTPS de los portales.
- `MESSAGING_STORAGE_DIR`: almacenamiento local de desarrollo.
- `MESSAGING_AZURE_CONNECTION_STRING` y `MESSAGING_AZURE_CONTAINER`:
  almacenamiento temporal privado de adjuntos en produccion.
- `MESSAGING_ATTACHMENT_DAYS`: retencion temporal, minimo 15 y 30 por defecto.
- `MESSAGING_GRAPH_*`: credenciales Graph y buzones de envio.
- `MESSAGING_STAFF_*`: acceso Microsoft 365 de empleados, dominio permitido y
  administradores iniciales.
- `MESSAGING_FIREBASE_CREDENTIALS`: ruta privada al JSON de cuenta de servicio
  usado por Firebase Admin para FCM.
- `MESSAGING_FIREBASE_CREDENTIALS_JSON`: JSON completo de la misma cuenta de
  servicio como variable secreta, util para Railway cuando no se monta un fichero.
- `MESSAGING_APP_REDIRECT_URI`: deep link del cliente movil; por defecto
  `es.gestinem.app://auth/callback`.
- `MESSAGING_SYNC_TOKEN`: secreto exclusivo del worker Synology.
- `MESSAGING_SMTP_*`: respaldo opcional si Graph no esta disponible.

La aplicacion Azure necesita los permisos Graph correspondientes; `Mail.Send`
de aplicacion es necesario para invitaciones, recuperaciones y avisos.

## Almacenamiento de adjuntos

Los adjuntos enviados desde Flutter permanecen temporalmente en Azure Blob. El
worker Synology los reclama, verifica su SHA-256, copia el contenido al
repositorio documental compartido y confirma la entrega. Solo entonces el
backend elimina la copia temporal.

El disco local configurado por `MESSAGING_STORAGE_DIR` es valido para desarrollo,
pero no es el archivo definitivo de produccion.

## Mensajeria movil y tiempo real

La ampliacion aditiva `backend/migrations/002_flutter_messaging.sql` incorpora
respuestas a mensajes, borrado logico con auditoria, grupos, campanas,
dispositivos de app y codigos de acceso de empleados. Debe aplicarse en
despliegues existentes antes de habilitar esas rutas.

Railway usa `railway.toml`, que construye `backend/Dockerfile`. Su comando de
produccion es `exec uvicorn backend.api.app:app --host 0.0.0.0 --port
${PORT:-8000} --proxy-headers`; sin `--workers`, Uvicorn arranca un unico worker.

`/api/v1/messaging/ws/{audience}` ofrece WebSocket autenticado. El hub actual es
en memoria y requiere mantener ese unico worker/proceso FastAPI; REST y el
endpoint de eventos siguen siendo la fuente de verdad y el fallback. Antes de
usar varios workers o escalar horizontalmente debe sustituirse el bus por
pub/sub compartido (Redis, PostgreSQL u otro equivalente), sin cambiar el
contrato exterior.
