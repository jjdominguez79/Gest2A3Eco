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
- Acceso de red al backend y a la base de datos local SQLite
- Plantilla Word en `plantillas_word/factura_emitida.docx`

---

## 2. Arquitectura del flujo

```
Flutter app  -->  Backend API (Railway)  <--  Worker (Windows)
                       |                         |
                  Azure Blob               Word COM + SQLite
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
| `CLIENT_DOCUMENTS_STORAGE_DIR` | `./client_documents_storage` | Fallback local |
| `MESSAGING_FIREBASE_CREDENTIALS` | - | Ruta a JSON Firebase |
| `MESSAGING_FIREBASE_CREDENTIALS_JSON` | - | JSON Firebase inline |
| `MESSAGING_SMTP_HOST` | - | Fallback SMTP si Graph no disponible |

---

## 4. Variables de entorno - Worker

| Variable | Default | Descripcion |
|----------|---------|-------------|
| `INVOICE_WORKER_API_URL` | `https://tramites.gestinem.es/api/v1/messaging/client/invoicing` | Endpoint del backend |
| `INVOICE_WORKER_API_TOKEN` | - | Token API (o Credential Manager) |
| `INVOICE_WORKER_DESKTOP_DSN` | - | DSN PostgreSQL escritorio |
| `INVOICE_WORKER_ID` | `worker-{pid}` | Identificador del worker |
| `INVOICE_WORKER_LEASE_MINUTES` | `10` | Duracion del lease |
| `INVOICE_WORKER_POLL_SECONDS` | `30` | Intervalo de sondeo |
| `INVOICE_WORKER_MAX_RETRIES` | `5` | Reintentos maximos |
| `INVOICE_WORKER_TEMPLATE_DIR` | `./plantillas_word` | Directorio de plantillas |
| `INVOICE_WORKER_PDF_DIR` | `./pdfs_generados` | Directorio de salida PDF |
| `INVOICE_WORKER_LOG_DIR` | `./logs` | Directorio de logs |
| `INVOICE_WORKER_GRAPH_SENDER` | `Oficina@gestinem.es` | Buzon remitente |

---

## 5. Procedimiento de activacion

### Paso 1: Verificar backend

```bash
# Comprobar que el backend responde
curl -s https://BACKEND_URL/api/v1/messaging/public/app-version?platform=windows

# Comprobar conexion a Azure Blob
curl -s -H "X-API-Key: $API_KEY" \
  https://BACKEND_URL/api/v1/messaging/client/invoicing/worker/claim \
  -d '{"worker_id":"health-check"}'
```

### Paso 2: Configurar credenciales del worker (Windows)

```powershell
# Opcion A: Variables de entorno
$env:INVOICE_WORKER_API_TOKEN = "token-del-backend"
$env:INVOICE_WORKER_DESKTOP_DSN = "postgresql://user:pass@localhost/gest2a3eco"

# Opcion B: Credential Manager (recomendado)
# El worker lee automaticamente de Windows Credential Manager:
#   - Gest2A3Eco_InvoiceWorkerApiToken
#   - Gest2A3Eco_InvoiceWorkerDesktopDSN
```

### Paso 3: Instalar y probar worker

```powershell
cd invoice_worker
pip install -r requirements.txt
python -m invoice_worker --dry-run   # verificar configuracion sin procesar
python -m invoice_worker             # ejecutar
```

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

## 6. Verificacion post-activacion

| Comprobacion | Comando / accion |
|-------------|------------------|
| Features visibles en app | Login como cliente de la org activada |
| Worker procesando | `tail -f logs/invoice_worker.log` |
| PDF en Azure | Portal Azure > contenedor `documentos-cliente` |
| Email enviado | Bandeja del destinatario |
| Auditoria de flags | `SELECT * FROM client_feature_flag_audit ORDER BY changed_at DESC;` |
| Estado factura | `SELECT id, status FROM client_invoices WHERE organization_id = '...' ORDER BY created_at DESC;` |
| Cola de procesamiento | `SELECT * FROM client_invoice_processing_queue WHERE queue_status != 'completed';` |

---

## 7. Troubleshooting

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

- Verificar que Word esta instalado: `python -c "import win32com.client; w=win32com.client.Dispatch('Word.Application'); w.Quit()"`
- Verificar credenciales: `python -c "from utils.credential_store import get_all; print(get_all())"`
- Verificar conectividad: `curl https://BACKEND_URL/api/v1/messaging/public/app-version`

### Email no enviado (status `rendered` pero no `emailed`)

1. Verificar `MESSAGING_GRAPH_FROM` configurado
2. Verificar permisos Graph (`Mail.Send` application permission)
3. Revisar logs del backend para errores 502 en `/send-email`
4. Si no hay destinatario, se marca `emailed` con razon `sin_destinatario` (correcto)

### Features no visibles en la app

1. Verificar flag global: `echo $CLIENT_DOCUMENTS_ENABLED` (debe ser `true`)
2. Verificar flag de org:
   ```sql
   SELECT company_code, client_documents_enabled, client_invoicing_enabled
   FROM msg_organizations WHERE company_code = 'CODIGO';
   ```
3. Ambos deben ser `true` para que el flag efectivo sea `true`
4. El cliente debe cerrar sesion y volver a entrar

---

## 8. Rollback

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
