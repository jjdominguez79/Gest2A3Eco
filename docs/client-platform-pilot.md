# Runbook: Piloto Plataforma Cliente (Documentos + Facturacion)

## 1. Requisitos previos

### Railway (backend)
- PostgreSQL >= 15 con extension `pgcrypto`
- Servicio web desplegado desde rama `main`
- Variables de entorno configuradas (ver seccion 3)

### Azure
- Cuenta de almacenamiento con dos contenedores:
  - `documentos-cliente` (permanente, para PDFs de facturas y documentos)
  - `mensajeria-temporal` (temporal, para adjuntos de chat)
- Registro de aplicacion en Azure AD (Graph API):
  - Permisos: `Mail.Send` (aplicacion), `User.Read` (delegado)
  - Secreto de cliente vigente

### Firebase (FCM)
- Proyecto Firebase con messaging habilitado
- Archivo de credenciales de servicio JSON

### Puesto Windows (worker)
- Windows 10/11 con Microsoft Word instalado (COM automation)
- Python 3.12+ con dependencias del worker
- Acceso de red al backend y a la base de datos PostgreSQL local
- Plantilla Word en `plantillas_word/factura_emitida.docx`

> **Importante:** Word COM y el Windows Credential Manager requieren el
> perfil interactivo del usuario. La tarea programada debe ejecutarse con
> el usuario logueado (opcion "Ejecutar solo cuando el usuario haya iniciado
> sesion"). NO usar "Ejecutar independientemente de si el usuario ha iniciado
> sesion" (S4U), ya que impide el acceso a COM y a las credenciales del usuario.

---

## 2. Arquitectura del flujo

```
Flutter app  -->  Backend API (Railway)  <--  Worker (Windows)
                       |                         |
                  Azure Blob              Word COM + PostgreSQL
                  Graph Mail
                  Firebase FCM
```

El worker NO tiene acceso directo a Azure, Graph ni Firebase.
Delega email y FCM al backend via endpoints REST.

---

## 3. Variables de entorno - Backend

### Obligatorias para el piloto

| Variable | Descripcion |
|----------|-------------|
| `DGT_DATABASE_URL` | Connection string PostgreSQL |
| `DGT_INTERNAL_API_KEY` | Clave API interna (compartida con worker y escritorio) |
| `CLIENT_DOCUMENTS_AZURE_CONNECTION_STRING` | Azure Blob para documentos permanentes |
| `MESSAGING_GRAPH_TENANT_ID` | Azure AD tenant |
| `MESSAGING_GRAPH_CLIENT_ID` | OAuth2 client ID |
| `MESSAGING_GRAPH_CLIENT_SECRET` | OAuth2 client secret |
| `MESSAGING_GRAPH_FROM` | Buzon remitente para emails de facturas |
| `MESSAGING_PUBLIC_BASE_URL` | URL base publica del backend |
| `MESSAGING_STAFF_ADMIN_EMAILS` | Emails de administradores (separados por coma) |
| `MESSAGING_STAFF_ALLOWED_DOMAIN` | Dominio permitido para staff |

### Feature flags (ambos `false` por defecto)

| Variable | Descripcion |
|----------|-------------|
| `CLIENT_DOCUMENTS_ENABLED` | Habilitar area documental globalmente |
| `CLIENT_INVOICING_ENABLED` | Habilitar facturacion online globalmente |

> **Importante:** El flag efectivo requiere AMBOS: global=true Y org=true.
> Activar el flag global sin activar la organizacion no tiene efecto.

### Opcionales

| Variable | Default | Descripcion |
|----------|---------|-------------|
| `CLIENT_DOCUMENTS_AZURE_CONTAINER` | `documentos-cliente` | Contenedor Azure |
| `CLIENT_DOCUMENTS_STORAGE_DIR` | `./client_documents_storage` | Solo para desarrollo/tests |
| `CLIENT_DOCUMENTS_ALLOW_LOCAL_STORAGE` | `false` | Permite fallback a disco (solo desarrollo/tests) |
| `MESSAGING_FIREBASE_CREDENTIALS` | - | Ruta a JSON Firebase |
| `MESSAGING_FIREBASE_CREDENTIALS_JSON` | - | JSON Firebase inline |
| `MESSAGING_SMTP_HOST` | - | Fallback SMTP si Graph no disponible |

> **Produccion:** `CLIENT_DOCUMENTS_AZURE_CONNECTION_STRING` es obligatorio
> cuando `CLIENT_DOCUMENTS_ENABLED` o `CLIENT_INVOICING_ENABLED` son `true`.
> El backend arranca con error si falta Azure y el flag esta activo.

---

## 4. Configuracion del worker Windows

### Secretos - Credential Manager (obligatorio en produccion)

Los secretos del worker se almacenan SIEMPRE en Windows Credential Manager.
Las variables de entorno solo se usan como fallback en desarrollo/tests.

```powershell
# Almacenar token API en Credential Manager
# Nombre: Gest2A3Eco/WorkstationToken
cmdkey /generic:"Gest2A3Eco/WorkstationToken" /user:"worker" /pass:"token-del-backend"

# Almacenar credenciales PostgreSQL en Credential Manager
# Nombre: Gest2A3Eco/PostgreSQL
cmdkey /generic:"Gest2A3Eco/PostgreSQL" /user:"gest2a3eco" /pass:"contrasena-postgres"
```

**No usar variables de entorno persistentes en produccion** para los secretos.
`INVOICE_WORKER_API_TOKEN` y `INVOICE_WORKER_DESKTOP_DSN` son exclusivamente
para desarrollo y tests.

### Variables de entorno del worker (no secretas)

| Variable | Default | Descripcion |
|----------|---------|-------------|
| `INVOICE_WORKER_API_URL` | `https://tramites.gestinem.es/api/v1/messaging/client/invoicing` | Endpoint del backend |
| `INVOICE_WORKER_ID` | `worker-{pid}` | Identificador del worker |
| `INVOICE_WORKER_LEASE_MINUTES` | `10` | Duracion del lease |
| `INVOICE_WORKER_POLL_SECONDS` | `30` | Intervalo de sondeo |
| `INVOICE_WORKER_MAX_RETRIES` | `5` | Reintentos maximos |
| `INVOICE_WORKER_TEMPLATE_DIR` | `./plantillas_word` | Directorio de plantillas |
| `INVOICE_WORKER_PDF_DIR` | `./pdfs_generados` | Directorio de salida PDF |
| `INVOICE_WORKER_LOG_DIR` | `./logs` | Directorio de logs |
| `INVOICE_WORKER_PG_HOST` | `localhost` | Host PostgreSQL |
| `INVOICE_WORKER_PG_PORT` | `5432` | Puerto PostgreSQL |
| `INVOICE_WORKER_PG_DB` | `gest2a3eco` | Base de datos PostgreSQL |

---

## 5. Migraciones de base de datos

Las migraciones se aplican en orden. El backend las aplica automaticamente
al arrancar si estan configuradas, o se pueden aplicar manualmente:

| Migracion | Descripcion |
|-----------|-------------|
| 008_client_platform_foundation.sql | Tablas base de la plataforma cliente |
| 009_client_documents.sql | Documentos del cliente |
| 010_client_invoicing.sql | Facturacion online |
| 011_messaging_notification_targets.sql | Destinos de notificacion |
| 012_feature_flag_audit.sql | Auditoria de feature flags |
| 013_notification_log.sql | Registro idempotente de notificaciones (email/FCM) |

```bash
# Aplicar manualmente si es necesario
psql $DATABASE_URL < backend/migrations/013_notification_log.sql
```

---

## 6. Procedimiento de activacion

### Paso 1: Verificar backend (diagnostico, no mutante)

```bash
# Comprobar que el backend responde (no mutante)
curl -s https://BACKEND_URL/health

# Comprobar autenticacion (GET es no mutante; 404 esperado, 401/403 indica problema)
curl -s -H "X-API-Key: $API_KEY" \
  https://BACKEND_URL/api/v1/messaging/client/invoicing/worker/invoice/test/status
```

### Paso 2: Configurar credenciales del worker (Windows)

```powershell
# Almacenar en Credential Manager (obligatorio en produccion)
cmdkey /generic:"Gest2A3Eco/WorkstationToken" /user:"worker" /pass:"TOKEN"
cmdkey /generic:"Gest2A3Eco/PostgreSQL" /user:"gest2a3eco" /pass:"PASS"
```

### Paso 3: Instalar y verificar worker

```powershell
cd invoice_worker
pip install -r requirements.txt

# Verificar configuracion sin procesar ninguna factura (no mutante)
python -m invoice_worker --dry-run

# Si el dry-run es exitoso, ejecutar el worker
python -m invoice_worker
```

El dry-run comprueba (sin modificar datos):
1. Token API (Credential Manager: `Gest2A3Eco/WorkstationToken`)
2. DSN PostgreSQL + conexion real (Credential Manager: `Gest2A3Eco/PostgreSQL`)
3. Microsoft Word COM disponible
4. Plantilla `.docx` en el directorio configurado
5. Conectividad al backend (`/health`)
6. Autenticacion con el backend (GET `/status` con ID ficticio)

Sale con codigo 0 si todo OK, 1 si hay errores criticos.

### Paso 4: Activar flags por organizacion

```bash
# 1. Activar flag global en Railway
# En Railway: CLIENT_DOCUMENTS_ENABLED=true, CLIENT_INVOICING_ENABLED=true

# 2. Activar por organizacion (como admin desde la app o API)
curl -X PATCH \
  -H "X-API-Key: $API_KEY" \
  -H "X-Device-Id: puesto-admin" \
  -H "X-Device-Token: $DEVICE_TOKEN" \
  -H "X-Staff-Id: admin-id" \
  -H "Content-Type: application/json" \
  https://BACKEND_URL/api/v1/messaging/staff/admin/organizations/CODIGO/features \
  -d '{"client_documents_enabled": true, "client_invoicing_enabled": true}'
```

### Paso 5: Verificar desde la app Flutter

1. Cerrar sesion y volver a entrar (para refrescar features)
2. Comprobar que aparece "Mis documentos" en el menu lateral
3. Comprobar que aparece "Facturacion" en el menu lateral
4. Crear un borrador de factura y emitirlo
5. Verificar que el worker lo procesa (logs del worker)
6. Verificar que el PDF aparece en "Mis documentos"
7. Verificar que se recibe el email (si hay destinatario)

---

## 7. Verificacion post-activacion

| Comprobacion | Comando / accion |
|-------------|------------------|
| Features visibles en app | Login como cliente de la org activada |
| Worker procesando | `tail -f logs/invoice_worker.log` |
| PDF en Azure | Portal Azure > contenedor `documentos-cliente` |
| Email enviado | Bandeja del destinatario |
| Auditoria de flags | `SELECT * FROM client_feature_flag_audit ORDER BY changed_at DESC;` |
| Estado factura | `SELECT id, status FROM client_invoices WHERE organization_id = '...' ORDER BY created_at DESC;` |
| Cola de procesamiento | `SELECT * FROM client_invoice_processing_queue WHERE queue_status != 'completed';` |
| Log de notificaciones | `SELECT * FROM client_invoice_notification_log ORDER BY created_at DESC;` |
| Entregas inciertas | `GET /api/v1/messaging/client/invoicing/worker/notification-health` con la clave interna |

---

## 8. Troubleshooting

### Factura atascada en `issued_pending_processing`

1. Verificar que el worker esta corriendo y conectado
2. Comprobar `client_invoice_processing_queue`: si `lease_expires_at` ya caduco, el worker lo reclamara automaticamente
3. Si `retry_count >= max_retries`, intervenir manualmente:
   ```sql
   UPDATE client_invoice_processing_queue
   SET retry_count = 0, queue_status = 'pending', error_message = ''
   WHERE invoice_id = 'xxx';
   UPDATE client_invoices SET status = 'issued_pending_processing' WHERE id = 'xxx';
   ```

### Worker no arranca

- Ejecutar dry-run para diagnostico: `python -m invoice_worker --dry-run`
- Verificar que Word esta instalado: `python -c "import comtypes.client; w=comtypes.client.CreateObject('Word.Application'); w.Quit()"`
- Verificar credenciales en Credential Manager: `cmdkey /list | findstr Gest2A3Eco`
- Verificar conectividad: `curl https://BACKEND_URL/health`
- Si el worker se ejecuta como tarea programada, asegurarse de que esta
  configurada para ejecutarse "solo cuando el usuario haya iniciado sesion"
  (no con S4U). Word COM y Credential Manager requieren perfil interactivo.

### Email no enviado (status `rendered` pero no `emailed`)

1. Verificar `MESSAGING_GRAPH_FROM` configurado en Railway
2. Verificar permisos Graph (`Mail.Send` application permission)
3. Revisar logs del backend para errores 502 en `/send-email`
4. Revisar `client_invoice_notification_log` para ver el historial de intentos
5. Si no hay destinatario, se genera evento `email_skipped` y el status
   de la factura permanece en `rendered` (correcto, no es un error)

### Token FCM invalido

El backend desactiva automaticamente el dispositivo cuando FCM devuelve un
fallo permanente. Verificar en `msg_app_devices`:
```sql
SELECT push_token, platform, active, updated_at
FROM msg_app_devices
WHERE user_type = 'client' AND active = false
ORDER BY updated_at DESC;
```

### Notificaciones en estado incierto

El endpoint interno y no mutante siguiente muestra entregas `sending` o
`unknown` con mas de 30 minutos:

```bash
curl -s -H "X-API-Key: $DGT_INTERNAL_API_KEY" \
  https://BACKEND_URL/api/v1/messaging/client/invoicing/worker/notification-health
```

No se reintentan automaticamente para evitar duplicados. Antes de permitir un
reintento manual hay que comprobar en Graph/Firebase si el proveedor acepto la
entrega. Solo cuando se confirme que no fue enviada se cambia su estado:

```sql
UPDATE client_invoice_notification_log
SET status = 'failed', detail = 'reintento manual autorizado', updated_at = NOW()
WHERE id = 123 AND status IN ('sending', 'unknown');
```

### Features no visibles en la app

1. Verificar flag global: en Railway, `CLIENT_DOCUMENTS_ENABLED` debe ser `true`
2. Verificar flag de org:
   ```sql
   SELECT company_code, client_documents_enabled, client_invoicing_enabled
   FROM msg_organizations WHERE company_code = 'CODIGO';
   ```
3. Ambos deben ser `true` para que el flag efectivo sea `true`
4. El cliente debe cerrar sesion y volver a entrar

---

## 9. Rollback

### Desactivar sin perder datos

```bash
# En Railway: volver flags a false
CLIENT_DOCUMENTS_ENABLED=false
CLIENT_INVOICING_ENABLED=false
```

Los datos (facturas, documentos, clientes) permanecen en la BD.
La app simplemente oculta las secciones.

### Rollback completo

1. Desactivar flags globales
2. Detener el worker
3. Los PDFs permanecen en Azure Blob (no se eliminan)
4. La BD mantiene todo el historico

> No es necesario revertir migraciones de esquema: las columnas adicionales
> no afectan al funcionamiento normal de la aplicacion.
