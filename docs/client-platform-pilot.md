# Runbook: fase 1 del area documental del cliente

Esta fase permite que el cliente consulte, guarde y comparta en Flutter las
facturas emitidas desde el escritorio. La creacion de facturas por el cliente
y su worker de Word quedan expresamente para la fase 2.

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

### Puesto de escritorio
- Gest2A3Eco configurado con la URL del backend.
- `Gest2A3Eco/WorkstationToken` guardado en Windows Credential Manager.
- Acceso de red al backend y al PostgreSQL habitual del escritorio.

No es necesaria una maquina virtual ni Microsoft Word adicional para esta
fase: el escritorio publica el PDF definitivo que ya genera actualmente.

---

## 2. Arquitectura del flujo

```
Flutter app  -->  Backend API (Railway)  <--  Gest2A3Eco (Windows)
                       |                            |
                  Azure Blob                 PDF ya emitido
                  Firebase FCM               Cola PostgreSQL
```

El escritorio no accede directamente a Azure ni Firebase. Publica el PDF por
la API autenticada; si falla, conserva la cola en PostgreSQL y reintenta.

---

## 3. Variables de entorno - Backend

### Obligatorias para el piloto

| Variable | Descripcion |
|----------|-------------|
| `DGT_DATABASE_URL` | Connection string PostgreSQL |
| `DGT_INTERNAL_API_KEY` | Clave API interna (compartida con worker y escritorio) |
| `CLIENT_DOCUMENTS_AZURE_CONNECTION_STRING` | Azure Blob para documentos permanentes |
| `MESSAGING_PUBLIC_BASE_URL` | URL base publica del backend |
| `MESSAGING_STAFF_ADMIN_EMAILS` | Emails de administradores (separados por coma) |
| `MESSAGING_STAFF_ALLOWED_DOMAIN` | Dominio permitido para staff |

### Feature flags

| Variable | Descripcion |
|----------|-------------|
| `CLIENT_DOCUMENTS_ENABLED` | Habilitar area documental globalmente |
| `CLIENT_INVOICING_ENABLED` | Facturacion creada por el cliente; mantener `false` en fase 1 |

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
> cuando `CLIENT_DOCUMENTS_ENABLED` es `true`.
> El backend arranca con error si falta Azure y el flag esta activo.

---

## 4. Configuracion del escritorio

### Secretos - Credential Manager (obligatorio en produccion)

El token del puesto se almacena en Windows Credential Manager.

```powershell
# Almacenar token API en Credential Manager en el mismo usuario que ejecuta Gest2A3Eco
# Nombre: Gest2A3Eco/WorkstationToken
cmdkey /generic:"Gest2A3Eco/WorkstationToken" /user:"worker" /pass:"token-del-backend"

```

En la configuracion local de Gest2A3Eco, `integrations_api_url` debe apuntar al
backend desplegado. No guardar el token ni contrasenas en el JSON local.

### Maquina virtual Synology (fase 2, no instalar ahora)

La maquina que figuraba en la planificacion era una **VM Windows 10/11 con
Microsoft Word**, destinada a ejecutar `invoice_worker` mediante Word COM para
las facturas creadas desde Flutter. No interviene en la consulta de facturas
emitidas por el escritorio y debe permanecer aplazada junto con
`CLIENT_INVOICING_ENABLED=false`.

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

### Paso 2: Configurar el puesto de escritorio

```powershell
# Almacenar en Credential Manager (obligatorio en produccion)
cmdkey /generic:"Gest2A3Eco/WorkstationToken" /user:"worker" /pass:"TOKEN"
```

Configurar `integrations_api_url` con la URL publica del backend y reiniciar el
escritorio.

### Paso 3: Verificar el almacenamiento documental

```bash
curl -s -H "X-API-Key: $API_KEY" \
  https://BACKEND_URL/api/v1/messaging/client/documents/internal/storage-health
```

Debe responder `backend: azure` y `ok: true` en produccion.

### Paso 4: Activar flags por organizacion

```bash
# 1. Activar flag global en Railway
# En Railway:
# CLIENT_DOCUMENTS_ENABLED=true
# CLIENT_INVOICING_ENABLED=false

# 2. Activar por organizacion (como admin desde la app o API)
curl -X PATCH \
  -H "X-API-Key: $API_KEY" \
  -H "X-Device-Id: puesto-admin" \
  -H "X-Device-Token: $DEVICE_TOKEN" \
  -H "X-Staff-Id: admin-id" \
  -H "Content-Type: application/json" \
  https://BACKEND_URL/api/v1/messaging/staff/admin/organizations/CODIGO/features \
  -d '{"client_documents_enabled": true, "client_invoicing_enabled": false}'
```

### Paso 5: Verificar desde la app Flutter

1. Cerrar sesion y volver a entrar (para refrescar features)
2. Comprobar que aparece "Mis documentos" en el menu lateral
3. En el escritorio, enviar por email una factura definitiva del mismo cliente
4. Verificar el estado `Area cliente: Publicada` en la lista de facturas
5. Verificar que el PDF aparece una sola vez en "Mis documentos > Facturas"
6. Abrirlo, guardarlo y compartirlo desde Flutter

---

## 7. Verificacion post-activacion

| Comprobacion | Comando / accion |
|-------------|------------------|
| Features visibles en app | Login como cliente de la org activada |
| PDF en Azure | Portal Azure > contenedor `documentos-cliente` |
| Auditoria de flags | `SELECT * FROM client_feature_flag_audit ORDER BY changed_at DESC;` |
| Estado local | Columna `Area cliente` de Facturas emitidas |
| Reintento manual | Boton `Reintentar area cliente` del escritorio |

---

## 8. Troubleshooting

### Publicacion pendiente o bloqueada

- `Pendiente/Reintentando`: comprobar red, URL del backend, token del puesto y
  el estado de Azure. La aplicacion reintenta con espera incremental.
- `Bloqueada`: revisar que el NIF de la factura identifica una unica
  organizacion activa y que esta tiene el area documental habilitada. Corregir
  el dato y pulsar `Reintentar area cliente`.

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
2. Los PDFs permanecen en Azure Blob (no se eliminan)
3. La BD mantiene todo el historico

> No es necesario revertir migraciones de esquema: las columnas adicionales
> no afectan al funcionamiento normal de la aplicacion.
