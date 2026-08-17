# Arquitectura de secretos — Gest2A3Eco

**Estado:** vigente desde la serie 1.7.x.

**Ultima revision contra el codigo:** 2026-08-15.

## Principio de seguridad

Las credenciales maestras de Azure, SignRequest, Dataprius, Microsoft Graph,
Azure Blob, Web Push y correo pertenecen al backend o a los contenedores que las
usan. Nunca se entregan al escritorio como respuesta de una API.

Cada puesto Windows conserva solo credenciales propias y revocables:

- usuario y contrasena de PostgreSQL;
- `WorkstationToken` para el backend;
- token de dispositivo de mensajeria, generado durante el alta automatica.

Todos ellos se guardan en Windows Credential Manager. El JSON local contiene
unicamente configuracion no sensible.

```text
Escritorio Windows
  |-- PostgreSQL principal (credencial propia del puesto)
  `-- HTTPS + WorkstationToken
         `-- Backend FastAPI / Railway
              |-- Azure Document Intelligence
              |-- SignRequest
              |-- Dataprius
              |-- Azure Blob temporal
              |-- Microsoft Graph / Web Push
              `-- Firebase Cloud Messaging

Workers Synology
  |-- mail-sync: certificado Graph + usuario PostgreSQL tecnico
  `-- messaging-sync: MESSAGING_SYNC_TOKEN + usuario PostgreSQL tecnico
```

## Configuracion del escritorio

La ubicacion activa es:

```text
%LOCALAPPDATA%\Gest2A3Eco\config.local.json
```

Los antiguos `config.json` y `config.local.json` situados junto a la aplicacion
solo se leen para migrar una instalacion que todavia no tenga configuracion en
`LOCALAPPDATA`.

Ejemplo sin secretos:

```json
{
  "templates_path": "plantillas/plantillas.json",
  "a3_base_path": "C:\\A3ECO",
  "database_engine": "postgres",
  "postgres_host": "192.168.0.18",
  "postgres_port": 5433,
  "postgres_database": "gest2a3eco",
  "postgres_user": "gest2a3eco",
  "word_templates_dir": "\\\\servidor\\Doc_Compartidos\\Plantillas",
  "ocr_motor_activo": "azure",
  "azure_doc_intelligence_model_id": "facturas-produccion-v1",
  "integrations_api_url": "https://gest2a3eco-production.up.railway.app",
  "messaging_api_url": "https://gest2a3eco-production.up.railway.app",
  "messaging_workstation_id": "PC-OFICINA-1",
  "firma_habilitada": true,
  "firma_categoria_firmados": "FIRMAS",
  "firma_max_mb": 15
}
```

No deben persistirse `postgres_dsn`, `workstation_token`, contrasenas, tokens,
API keys ni connection strings. `save_app_config()` elimina todas las claves
sensibles conocidas antes de escribir.

`GEST2A3ECO_POSTGRES_DSN` se admite para automatizacion o migracion. Si un DSN
legacy contiene una contrasena, la aplicacion separa host, puerto, base y usuario,
guarda la credencial en Credential Manager y evita volver a escribir el DSN.

## Windows Credential Manager

Los servicios activos definidos por `utils/credential_store.py` incluyen:

| Servicio | Uso |
|---|---|
| `Gest2A3Eco/PostgreSQL` | Usuario y contrasena PostgreSQL |
| `Gest2A3Eco/WorkstationToken` | Token revocable del puesto |
| `Gest2A3Eco/MessagingDevice` | Token del dispositivo de mensajeria |
| `Gest2A3Eco/DesmarcarGeneradas` | Credencial de la operacion protegida |

Las entradas Azure y Azure Storage solo conservan compatibilidad con el modo
local sin backend. En produccion, OCR se delega al backend y las claves Azure no
se cargan en el escritorio.

Para provisionar interactivamente un puesto:

```powershell
python -m utils.provision_workstation --only-token
```

El valor tambien puede suministrarse temporalmente mediante
`GEST2A3ECO_WORKSTATION_TOKEN`.

## Autenticacion del backend

Los endpoints usan la cabecera `X-API-Key`, pero el tipo de credencial permitido
depende de la ruta:

- **`DGT_INTERNAL_API_KEY`:** administracion, workers y operaciones internas.
  Nunca se instala en los puestos.
- **`WorkstationToken`:** DGT, OCR, firma, Dataprius, sincronizacion autorizada y
  alta/actualizacion del dispositivo de escritorio.
- **Token de dispositivo:** complementa al `WorkstationToken` en mensajeria.
- **`MESSAGING_SYNC_TOKEN`:** exclusivo del worker de adjuntos de Synology.
- **Cookies de sesion:** portales web de clientes y empleados.

Cada `WorkstationToken` se genera con prefijo `g2a3_wks_`; el backend almacena
solo su hash SHA-256, permite revocarlo y actualiza `last_seen_at` al autenticar.

## Secretos del backend

Variables principales de Railway:

| Grupo | Variables |
|---|---|
| Nucleo | `DGT_DATABASE_URL`, `DGT_INTERNAL_API_KEY`, `DGT_PUBLIC_BASE_URL` |
| OCR | `AZURE_DOC_INTELLIGENCE_ENDPOINT`, `AZURE_DOC_INTELLIGENCE_KEY`, `AZURE_DOC_INTELLIGENCE_MODEL_ID` |
| Aprendizaje OCR | `AZURE_OCR_TRAINING_CONNECTION_STRING`, `AZURE_OCR_TRAINING_CONTAINER` |
| Firma | `SIGNREQUEST_TOKEN`, `SIGNREQUEST_FROM_EMAIL`, `SIGNREQUEST_GESTOR_EMAIL`, `SIGNREQUEST_GESTOR_TELEFONO` |
| Dataprius | `DATAPRIUS_API_KEY`, `DATAPRIUS_API_SECRET`, `DATAPRIUS_BASE_URL`, `DATAPRIUS_BASE_PATH` |
| Mensajeria | `MESSAGING_AZURE_*`, `MESSAGING_GRAPH_*`, `MESSAGING_STAFF_*`, `MESSAGING_VAPID_*`, `MESSAGING_SMTP_*` |
| App movil | `MESSAGING_FIREBASE_CREDENTIALS`, `MESSAGING_APP_REDIRECT_URI` |
| Worker | `MESSAGING_SYNC_TOKEN` |

`DGT_STORAGE_DIR` y `MESSAGING_STORAGE_DIR` son almacenamiento local de
desarrollo, no sustituyen el almacenamiento privado configurado en produccion.
El fichero apuntado por `MESSAGING_FIREBASE_CREDENTIALS` es una cuenta de
servicio y debe montarse como secreto; nunca se incorpora al repositorio ni al
paquete Flutter. `MESSAGING_APP_REDIRECT_URI` no es secreto.

## Provision, revocacion y rotacion

1. Un administrador crea el puesto con
   `POST /api/v1/admin/workstations`, autenticado mediante
   `DGT_INTERNAL_API_KEY`.
2. El token devuelto se muestra una sola vez y se introduce con
   `python -m utils.provision_workstation --only-token`.
3. El puesto comprueba `GET /api/v1/integrations/status` y completa el alta del
   dispositivo de mensajeria automaticamente.
4. Para revocar, el administrador usa
   `PATCH /api/v1/admin/workstations/{id}` con `{"active": false}`.

Para rotar un secreto de proveedor, generar la nueva credencial, sustituir la
variable correspondiente en Railway, redesplegar y verificar `/health` y
`/api/v1/integrations/status`. Para rotar un puesto, crear un token nuevo,
provisionarlo y desactivar el anterior.

La contrasena PostgreSQL se cambia en el servidor y despues en cada puesto desde
la configuracion PostgreSQL de la aplicacion; se guarda directamente en
Credential Manager.

## Compatibilidad y legado

Las instalaciones antiguas pueden contener `azure_doc_intelligence_key`,
`azure_storage_connection_string`, `dataprius_api_key`,
`dataprius_api_secret`, `signrequest_token`, `dgt_api_key`,
`integrations_api_key`, `messaging_api_key` o un DSN completo. Deben rotarse las
credenciales que estuvieron expuestas y dejar que la migracion las retire del
JSON.

Las API keys `dgt_api_key` e `integrations_api_key` ya no autentican al
escritorio. No deben restaurarse como mecanismo de rollback. Un rollback de
codigo debe conservar la separacion de secretos o hacerse solo con un plan de
rotacion explicito.

## Pendiente

- Eliminar a largo plazo la conexion PostgreSQL directa desde los puestos.
- Incorporar un panel web completo de administracion de puestos.
- Anadir rate limiting y rotacion automatica con caducidad para tokens de puesto.
