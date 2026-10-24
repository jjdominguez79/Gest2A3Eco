# API de facturacion autonoma de clientes

Contrato vivo. Se actualiza en cada etapa de `docs/adr/0001-facturacion-autonoma-cliente.md`.
Prefijo comun: `/api/v1/messaging/client/invoicing`.

## 1. Cliente (sesion `msg_session`, `organization_id` siempre de la sesion)

| Metodo | Ruta | Etapa | Notas |
|---|---|---|---|
| GET | `/config` | existente | flags + series + (Etapa 9) perfil fiscal del emisor |
| GET/POST | `/customers` | existente | alta inmediata, sin requerir escritorio |
| GET/POST/PUT/DELETE | `/drafts`, `/drafts/{id}` | existente | CRUD de borradores |
| POST | `/drafts/{id}/issue` | existente, **Etapa 3 quita el bloqueo por escritorio** | header `Idempotency-Key` obligatorio |
| GET | `/invoices`, `/invoices/{id}` | existente | **Etapa 2** anade los 5 estados separados a la respuesta |
| GET/POST | `/catalog/items` | **Etapa 4 (nuevo)** | catalogo de productos/servicios |
| POST | `/invoices/{id}/rectify` | **Etapa 7 (nuevo)** | crea factura rectificativa referenciando la original |
| POST | `/invoices/{id}/cancel` | **Etapa 7 (nuevo)** | registro de anulacion cuando corresponda |
| GET | `/invoices/combined` | **Etapa 10 (nuevo)** | listado unificado `client_app` + `desktop` (desktop solo lectura) |

## 2. `billing_worker` (credencial exclusiva `BILLING_WORKER_API_KEY`, Etapa 3/5)

Reemplaza el uso que hace hoy `require_workstation_or_internal` en estos
endpoints. El worker de escritorio deja de llamarlos (seccion 16 del
encargo).

| Metodo | Ruta | Job type |
|---|---|---|
| POST | `/worker/claim` | reclama el siguiente trabajo de `ClientInvoiceProcessingQueue` |
| GET | `/worker/invoice/{id}/payload` | datos completos para renderizar |
| POST | `/worker/invoice/{id}/pdf` | `render_pdf` → sube a Azure, verifica SHA-256 |
| POST | `/worker/invoice/{id}/publish-document` | `publish_document` |
| POST | `/worker/invoice/{id}/send-email` | `send_email`, idempotente |
| POST | `/worker/invoice/{id}/send-fcm` | `send_notification`, idempotente |
| POST | `/worker/invoice/{id}/error` | libera el lease, incrementa `retry_count` |
| GET | `/worker/invoice/{id}/status` | estado agregado |
| GET | `/worker/notification-health` | entregas `sending`/`unknown` &gt; 30 min |
| POST | `/worker/invoice/{id}/fiscal-register` | **Etapa 7 (nuevo)**: `fiscal_registration` |
| POST | `/worker/invoice/{id}/fiscal-cancel` | **Etapa 7 (nuevo)**: `fiscal_cancellation` |

## 3. `invoice_worker` desktop (credencial de puesto, sin cambios de transporte)

| Metodo | Ruta | Job type |
|---|---|---|
| POST | `/worker/customer/claim` | alta Flutter pendiente de tercero/subcuenta |
| POST | `/worker/customer/{id}/confirm` | confirma tercero+subcuenta 430 |
| POST | `/worker/customer/{id}/error` | libera para reintento, registra discrepancia |
| POST | `/worker/customer-sync`, `/worker/series-sync` | snapshot periodico (sin cambios) |
| POST | `/worker/accounting/claim` | **Etapa 3 (nuevo)**: reclama `ClientInvoiceAccountingQueue` |
| POST | `/worker/accounting/{id}/confirm` | **Etapa 3 (nuevo)**: `create_accounting_export` completado |
| POST | `/worker/accounting/{id}/error` | **Etapa 3 (nuevo)**: libera para reintento |
| POST | `/worker/desktop-invoices/sync` | **Etapa 10 (nuevo)**: proyecta cabeceras de facturas desktop |

## 4. Reglas de autoria (sin cambios, confirmadas en el codigo)

`organization_id` nunca se acepta del body/payload en los endpoints de
cliente: siempre se deriva de la sesion (`_authenticated_client`). Los
endpoints `/worker/*` nunca aceptan `organization_id` de cliente final; lo
resuelven desde la fila reclamada.
