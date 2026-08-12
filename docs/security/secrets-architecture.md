# Arquitectura de Secretos — Gest2A3Eco

## Arquitectura anterior (v1.6.x)

Cada puesto Windows almacenaba en `config.local.json` o `config.json`:

- Credenciales Azure Document Intelligence (endpoint + API key)
- Connection string de Azure Storage
- API key y secret de Dataprius
- Token de SignRequest
- DSN completo de PostgreSQL (incluyendo password)
- API keys compartidas para el backend (`dgt_api_key`, `integrations_api_key`)

Esto significaba que las credenciales maestras de servicios de pago/cloud
estaban replicadas en todos los PCs de la instalación.

## Arquitectura nueva (rama feature/backend-secrets en adelante)

```
Escritorio Windows
    │
    │  HTTPS + workstation_token (por puesto)
    ▼
Backend FastAPI (Railway)
    │
    ├── AZURE_DOC_INTELLIGENCE_KEY  →  Azure Document Intelligence
    ├── AZURE_OCR_TRAINING_*        →  Azure Blob Storage (entrenamiento)
    ├── SIGNREQUEST_TOKEN           →  SignRequest (firma electronica)
    ├── DATAPRIUS_API_KEY/SECRET    →  Dataprius (almacenamiento)
    └── DGT_DATABASE_URL            →  PostgreSQL (Railway)
```

**Regla:** Las credenciales maestras de proveedores externos NUNCA llegan
al escritorio como respuesta de API. El escritorio solo envía documentos
y recibe resultados procesados.

---

## Secretos del backend (variables de entorno en Railway)

| Variable | Descripción | Requerida |
|---------|-------------|-----------|
| `DGT_DATABASE_URL` | DSN PostgreSQL del backend | Sí |
| `DGT_INTERNAL_API_KEY` | Clave admin para endpoints internos | Sí |
| `DGT_PUBLIC_BASE_URL` | URL pública del backend | Sí |
| `AZURE_DOC_INTELLIGENCE_ENDPOINT` | Endpoint Azure OCR | Para OCR |
| `AZURE_DOC_INTELLIGENCE_KEY` | API Key Azure OCR | Para OCR |
| `AZURE_DOC_INTELLIGENCE_MODEL_ID` | ID modelo (default: prebuilt-invoice) | Opcional |
| `AZURE_OCR_TRAINING_CONNECTION_STRING` | Azure Blob para entrenamiento | Para training |
| `AZURE_OCR_TRAINING_CONTAINER` | Contenedor blob (default: facturas-entrenamiento) | Opcional |
| `SIGNREQUEST_TOKEN` | Token de autenticación SignRequest | Para firma |
| `SIGNREQUEST_FROM_EMAIL` | Email remitente firma | Para firma |
| `SIGNREQUEST_GESTOR_EMAIL` | Email del gestor en firmas | Opcional |
| `DATAPRIUS_API_KEY` | Client ID OAuth2 Dataprius | Para DGT |
| `DATAPRIUS_API_SECRET` | Client secret OAuth2 Dataprius | Para DGT |
| `DATAPRIUS_BASE_URL` | URL API Dataprius | Opcional |
| `DATAPRIUS_BASE_PATH` | Ruta base carpetas Dataprius | Opcional |
| `MESSAGING_AZURE_CONNECTION_STRING` | Azure Blob para mensajería | Para mensajería |
| `MESSAGING_GRAPH_TENANT_ID` | Tenant Azure AD para Graph | Para mensajería |
| `MESSAGING_GRAPH_CLIENT_ID` | Client ID Azure AD | Para mensajería |
| `MESSAGING_GRAPH_CLIENT_SECRET` | Client secret Azure AD | Para mensajería |
| `MESSAGING_VAPID_PUBLIC_KEY` | Clave pública VAPID (push) | Para push |
| `MESSAGING_VAPID_PRIVATE_KEY` | Clave privada VAPID | Para push |
| `MESSAGING_SYNC_TOKEN` | Token worker sincronización | Para sync |

---

## Configuración local del escritorio (config.local.json)

Solo contiene información **no sensible**. Ejemplo de configuración completa:

```json
{
  "templates_path": "plantillas/plantillas.json",
  "a3_base_path": "C:\\A3ECO\\",
  "word_templates_dir": "\\\\servidor\\Doc_Compartidos\\Plantillas",
  "documentos_output_dir": "\\\\servidor\\Doc_Compartidos\\Gest2A3Eco\\Empresas",
  "ocr_motor_activo": "azure",
  "azure_doc_intelligence_endpoint": "https://mi-recurso.cognitiveservices.azure.com/",
  "integrations_api_url": "https://tramites.gestinem.es",
  "integrations_api_key": "",
  "workstation_token": "g2a3_wks_XXXX",
  "messaging_api_url": "https://tramites.gestinem.es",
  "messaging_workstation_id": "PC-OFICINA-1",
  "database_engine": "postgres",
  "postgres_host": "192.168.0.18",
  "postgres_port": 5433,
  "postgres_database": "gest2a3eco",
  "postgres_user": "gest2a3eco",
  "signrequest_base_url": "https://signrequest.com/api/v1",
  "firma_habilitada": true,
  "firma_categoria_firmados": "FIRMAS",
  "firma_max_mb": 15
}
```

**No debe contener:** `azure_doc_intelligence_key`, `azure_storage_connection_string`,
`dataprius_api_key`, `dataprius_api_secret`, `signrequest_token`,
`dgt_api_key` (sustituido por `workstation_token`), `postgres_dsn` con password.

---

## Windows Credential Manager (psycopg/keyring)

La password de PostgreSQL se almacena en el almacén seguro de Windows:

| Servicio | Usuario | Contenido |
|---------|---------|-----------|
| `Gest2A3Eco/PostgreSQL` | `db_user` | `usuario:password` |
| `Gest2A3Eco/DesmarcarGeneradas` | `desmarcar` | hash scrypt de la contraseña |

**Migración automática:** Al arrancar, si `postgres_dsn` contiene password,
la aplicación la extrae, la guarda en Credential Manager y elimina el DSN del JSON.

**Fallback:** Si `keyring` no está disponible (entornos sin GUI, cuentas de servicio),
se mantiene el DSN con password y se registra un warning en el log.

---

## Autenticación de puestos (workstation tokens)

### Modelo

Cada puesto Windows tiene un token único con formato `g2a3_wks_<aleatorio>`.
El backend guarda solo el hash SHA-256, nunca el token en claro.

```
Tabla: workstations
  id            UUID
  name          VARCHAR(120) UNIQUE
  token_hash    VARCHAR(64)  -- SHA-256 del token
  active        BOOLEAN
  created_at    TIMESTAMP
  last_seen_at  TIMESTAMP
```

### Provisionar un puesto nuevo

1. Obtener la `DGT_INTERNAL_API_KEY` del backend (Railway → Variables).
2. Llamar al endpoint de administración:
   ```bash
   curl -X POST https://tramites.gestinem.es/api/v1/admin/workstations \
     -H "X-API-Key: TU_INTERNAL_KEY" \
     -H "Content-Type: application/json" \
     -d '{"name": "PC-OFICINA-3"}'
   ```
3. Copiar el campo `token` de la respuesta (solo se muestra una vez).
4. En el PC, editar `config.local.json` y añadir:
   ```json
   "workstation_token": "g2a3_wks_VALOR_RECIBIDO"
   ```
   O configurar la variable de entorno: `GEST2A3ECO_WORKSTATION_TOKEN`.

### Revocar un puesto

```bash
curl -X PATCH https://tramites.gestinem.es/api/v1/admin/workstations/WORKSTATION_ID \
  -H "X-API-Key: TU_INTERNAL_KEY" \
  -H "Content-Type: application/json" \
  -d '{"active": false}'
```

El puesto queda bloqueado inmediatamente. Los demás puestos no se ven afectados.

### Listar puestos y actividad

```bash
curl https://tramites.gestinem.es/api/v1/admin/workstations \
  -H "X-API-Key: TU_INTERNAL_KEY"
```

---

## Procedimiento de rotación de credenciales

### Backend (Railway)

1. Generar nueva credencial en el proveedor correspondiente.
2. Actualizar la variable de entorno en Railway → Settings → Variables.
3. Redeploy (Railway lo hace automáticamente).
4. Verificar `GET /health` y `GET /api/v1/integrations/status`.

### Workstation token de un puesto

1. Crear nuevo token: `POST /api/v1/admin/workstations` con el mismo nombre (o diferente).
2. Actualizar `config.local.json` en el PC con el nuevo token.
3. Deshabilitar el token antiguo: `PATCH /api/v1/admin/workstations/{id_antiguo}` con `{"active": false}`.

### Password PostgreSQL (escritorio)

1. Cambiar password en PostgreSQL del Synology.
2. En cada PC, abrir la aplicación y usar el menú de reconfiguración PostgreSQL.
   La nueva password se guardará en Windows Credential Manager automáticamente.

---

## Credenciales a rotar tras la migración inicial

Las siguientes credenciales estuvieron expuestas en `config.local.json` y
deben rotarse en sus respectivos proveedores:

| Credencial | Proveedor | Acción |
|-----------|-----------|--------|
| `azure_doc_intelligence_key` | Azure Portal → Document Intelligence | Regenerar key |
| `azure_storage_connection_string` | Azure Portal → Storage Account | Regenerar access key |
| `dataprius_api_key` / `dataprius_api_secret` | Panel Dataprius | Regenerar credenciales OAuth2 |
| `signrequest_token` | Panel SignRequest | Regenerar API token |
| `dgt_api_key` / `integrations_api_key` | Backend (variable propia) | Sustituir por workstation tokens |
| Password PostgreSQL | Synology DS920+ | `ALTER USER gest2a3eco PASSWORD 'nueva_password'` |

---

## Variables a crear en Railway antes del primer despliegue

```
AZURE_DOC_INTELLIGENCE_ENDPOINT=https://mi-recurso.cognitiveservices.azure.com/
AZURE_DOC_INTELLIGENCE_KEY=<nueva_key_rotada>
AZURE_DOC_INTELLIGENCE_MODEL_ID=prebuilt-invoice
AZURE_OCR_TRAINING_CONNECTION_STRING=<connection_string_rotado>
AZURE_OCR_TRAINING_CONTAINER=facturas-entrenamiento
```

(El resto de variables ya deberían estar configuradas en Railway.)

---

## Cambios necesarios en los PCs de escritorio

1. Actualizar la aplicación a la versión con la nueva rama.
2. En el primer arranque, la migración de `postgres_dsn` se ejecuta automáticamente.
3. Solicitar un `workstation_token` al administrador del backend.
4. Añadir `workstation_token` a la configuración local.
5. Verificar que `config.local.json` ya no contiene:
   - `azure_doc_intelligence_key`
   - `dataprius_api_key` / `dataprius_api_secret`
   - `signrequest_token`
   - `postgres_dsn` (con password)
6. Si quedaran esas claves de una instalación antigua, la aplicación las ignora
   con un warning en el log y continúa correctamente.

---

## Rollback

Si hay que revertir a la versión anterior:

1. Volver al commit anterior en la rama `main`.
2. Restaurar las variables en `config.local.json` desde las copias de seguridad.
3. Las credenciales en Windows Credential Manager no interfieren con la versión anterior.
4. Los workstation tokens del backend no afectan a versiones anteriores del escritorio.

---

## Aspectos pendientes (segunda fase)

- Migrar la capa de datos PostgreSQL del escritorio a endpoints REST del backend
  (eliminar la conexión directa a BD desde los PCs).
- Panel web de administración de puestos (actualmente solo via API).
- Rate limiting en los nuevos endpoints.
- Rotación automática de workstation tokens con TTL.
- Mover la configuración de Microsoft Graph del escritorio al backend.
