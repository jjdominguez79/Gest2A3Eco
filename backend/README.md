# Backend de integraciones y mensajeria

Backend FastAPI independiente del escritorio. Sirve los tramites DGT, OCR
Azure, SignRequest, Dataprius y las API que consume la aplicacion Flutter.
Revisado contra el codigo el 2026-09-03.

## Desarrollo local

```powershell
python -m pip install -r backend/requirements.txt
$env:BACKEND_DATABASE_URL = "postgresql+psycopg://usuario:password@localhost:5432/gest2a3eco_backend"
$env:BACKEND_INTERNAL_API_KEY = "secreto-solo-desarrollo"
$env:BACKEND_PUBLIC_BASE_URL = "http://localhost:8000"
python -m uvicorn backend.api.app:app --reload
```

Comprobaciones:

- `GET /health`
- OpenAPI en `/docs` y `/openapi.json`
- portal DGT en `/t/{referencia}/{rol}`
- aplicacion Flutter Web en `https://app.gestinem.es`

La base del backend es PostgreSQL y se configura exclusivamente mediante
`BACKEND_DATABASE_URL`. No existe fallback a SQLite. El esquema inicial esta en
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
- **Aplicacion Flutter:** cliente web y nativo para clientes y empleados, con
  codigos de acceso, registro/presencia de dispositivos y WebSocket.
- **Worker de adjuntos:** endpoints tecnicos para reclamar, descargar, verificar
  y confirmar archivos temporales.

## Autenticacion

La cabecera `X-API-Key` tiene dos credenciales posibles segun la ruta:

- `BACKEND_INTERNAL_API_KEY`: administracion de puestos y organizaciones,
  invitaciones internas y otras rutas exclusivas del servidor.
- `CLIENT_MASTER_SYNC_API_KEY`: sincronizacion unidireccional de perfiles,
  clientes y serie online desde el Synology; debe ser una clave distinta.
- `WorkstationToken`: operaciones del escritorio en DGT, OCR, firma,
  Dataprius, estado de integraciones y alta del dispositivo de mensajeria.

Un `WorkstationToken` no puede acceder a endpoints administrativos. Flutter
usa sesiones propias y el worker de adjuntos usa `X-Sync-Token` con
`MESSAGING_SYNC_TOKEN`.

En cada puesto se configuran las URLs `integrations_api_url` y
`messaging_api_url`; el token se guarda en Windows Credential Manager, nunca en
el JSON local. En el primer acceso, el escritorio obtiene un token de dispositivo
revocable y tambien lo guarda en Credential Manager.

## Variables de entorno

### Nucleo del backend

- `BACKEND_DATABASE_URL`: DSN SQLAlchemy PostgreSQL obligatorio.
- `BACKEND_INTERNAL_API_KEY`: credencial interna obligatoria fuera de pruebas.
- `CLIENT_MASTER_SYNC_API_KEY`: credencial exclusiva del worker maestro.
- `BACKEND_PUBLIC_BASE_URL`: origen comun del servicio. DGT y mensajeria lo
  heredan si no definen un origen especifico.

### DGT

- `DGT_PUBLIC_BASE_URL`: anulacion opcional del origen para enlaces DGT.
- `DGT_TOKEN_TTL_HOURS`: caducidad de enlaces; 168 horas por defecto.
- `DGT_STORAGE_DIR`: almacenamiento privado local de desarrollo.

Durante la migracion, el backend acepta `DGT_DATABASE_URL` y
`DGT_INTERNAL_API_KEY` como alias heredados. Si existe tambien el nombre
`BACKEND_*`, este tiene prioridad. Los alias antiguos deben retirarse de
Railway despues de verificar el primer despliegue con los nombres nuevos.

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

- `MESSAGING_PUBLIC_BASE_URL`: origen HTTPS publico del backend.
- `MESSAGING_APP_WEB_URL`: origen de Flutter Web; por defecto
  `https://app.gestinem.es`.
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
- `MESSAGING_APP_REDIRECT_URI`: deep link del cliente nativo; por defecto
  `es.gestinem.app://auth/callback`.
- `MESSAGING_APP_WEB_REDIRECT_URI`: callback de autenticacion de Flutter Web.
- `MESSAGING_SYNC_TOKEN`: secreto exclusivo del worker Synology.
- `MESSAGING_PRE_RELEASE_CLEANUP_ENABLED`: habilita excepcionalmente la purga
  global previa a la publicacion; `false` por defecto.
- `MESSAGING_SMTP_*`: respaldo opcional si Graph no esta disponible.

La aplicacion Azure necesita los permisos Graph correspondientes; `Mail.Send`
de aplicacion es necesario para invitaciones, recuperaciones, avisos y facturas.
El escritorio envia estas ultimas mediante `POST /api/v1/mail/send`, autenticado
con su `WorkstationToken`. Las credenciales de Graph permanecen exclusivamente
en el backend y nunca se configuran en cada puesto.

## Almacenamiento de adjuntos

Los adjuntos enviados desde Flutter permanecen temporalmente en Azure Blob. El
worker Synology los reclama, verifica su SHA-256, copia el contenido al
repositorio documental compartido y confirma la entrega. Solo entonces el
backend elimina la copia temporal.

El disco local configurado por `MESSAGING_STORAGE_DIR` es valido para desarrollo,
pero no es el archivo definitivo de produccion.

## Limpieza de mensajeria de prueba

Las organizaciones de prueba se identifican con `msg_organizations.is_test`.
Las historicas `E0000` y `E00000` se marcan automaticamente al aplicar la
migracion `008_test_data_cleanup.sql` o al arrancar una version actualizada.
El campo tambien puede establecerse mediante el alta/actualizacion administrativa
de organizaciones; nunca debe marcarse una empresa real.

La herramienta siempre funciona primero como previsualizacion y solo considera
organizaciones que tengan dicha marca:

```powershell
python -m backend.tools.limpiar_mensajeria --antes-de 2026-08-01
python -m backend.tools.limpiar_mensajeria --organizacion E00000 --reset-test
```

La salida incluye cantidades y un codigo ligado al contenido exacto del plan.
Para ejecutar se repite el mismo comando añadiendo el codigo, el responsable y
el motivo:

```powershell
python -m backend.tools.limpiar_mensajeria --organizacion E00000 --reset-test `
  --confirmar LIMPIAR-XXXXXXXXXXXX --actor "Nombre administrador" `
  --motivo "Fin de pruebas Flutter"
```

`--antes-de` conserva organizaciones, clientes, conversaciones y mensajes
posteriores a la fecha; las fechas sin zona horaria se interpretan como UTC.
`--reset-test` elimina por completo las organizaciones
de prueba seleccionadas. La operacion queda registrada en `msg_cleanup_audit`.
Los blobs se eliminan despues de confirmar la transaccion PostgreSQL; cualquier
fallo queda guardado en esa auditoria para su recuperacion manual.

### Purga global antes de publicar Flutter

Mientras la aplicacion no se haya publicado puede habilitarse temporalmente:

```text
MESSAGING_PRE_RELEASE_CLEANUP_ENABLED=true
```

La purga global no depende de `is_test`: elimina los mensajes anteriores al
corte de todas las empresas y los chats internos de empleados, pero conserva
empresas, clientes, empleados, sesiones, dispositivos, conversaciones e hilos.
Primero se previsualiza:

```powershell
python -m backend.tools.limpiar_mensajeria `
  --prepublicacion-antes-de "2026-08-30T00:00:00+02:00"
```

Despues se repite el mismo comando con `--confirmar`, `--actor` y `--motivo`.
Durante la ejecucion el backend rechaza temporalmente las escrituras de
mensajeria con HTTP 503. Si el proceso se interrumpe de forma abrupta, el
bloqueo se puede retirar de forma auditada:

```powershell
python -m backend.tools.limpiar_mensajeria --recuperar-mantenimiento
```

Al publicar Flutter se cierra para siempre el modo global desde la herramienta:

```powershell
python -m backend.tools.limpiar_mensajeria --cerrar-prepublicacion
```

Ambas operaciones muestran primero la frase exacta de confirmacion. El cierre
queda almacenado en PostgreSQL y prevalece aunque la variable de entorno vuelva
a activarse accidentalmente. Despues del cierre debe retirarse tambien
`MESSAGING_PRE_RELEASE_CLEANUP_ENABLED` del entorno.

La herramienta elimina los blobs temporales del backend. No borra copias que el
worker ya haya archivado en el repositorio documental compartido; esas copias
requieren un procedimiento separado para evitar afectar documentos reales.

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

## Solicitudes de modificación de empresa

Flutter no actualiza directamente los datos maestros. El cliente puede proponer
cambios de razón social, NIF, domicilio, contacto, cuentas bancarias y logotipo
mediante `POST /api/v1/messaging/client/profile-change-requests`. Cada solicitud
guarda una instantánea de los valores vigentes y crea un mensaje en el canal
privado, por lo que el personal recibe el aviso FCM habitual. El logotipo se
adjunta al mensaje y lo recoge el worker de adjuntos existente. Las solicitudes
permanecen `pending` hasta que un administrador las marca `applied` o `rejected`.
Al aprobar una solicitud con imagen, esa imagen pasa a ser el logotipo
corporativo visible en Flutter. Los restantes cambios no modifican
automaticamente PostgreSQL del escritorio.
