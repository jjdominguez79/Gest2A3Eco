# API de facturacion autonoma de clientes

Contrato vivo. Se actualiza en cada etapa de `docs/adr/0001-facturacion-autonoma-cliente.md`.
Prefijo comun: `/api/v1/messaging/client/invoicing`.

## 1. Cliente (sesion `msg_session`, `organization_id` siempre de la sesion)

| Metodo | Ruta | Etapa | Notas |
|---|---|---|---|
| GET | `/config` | existente | flags + series + (Etapa 9) perfil fiscal del emisor |
| GET/POST | `/customers` | existente | alta inmediata, sin requerir escritorio |
| GET/POST/PUT/DELETE | `/drafts`, `/drafts/{id}` | existente | CRUD de borradores |
| POST | `/drafts/{id}/issue` | **Etapa 3: bloqueo por escritorio eliminado** | header `Idempotency-Key` obligatorio; `pending_desktop_import`/`desktop_subcuenta` ya no condicionan la emision |
| GET | `/invoices`, `/invoices/{id}` | existente | **Etapa 2** anade los 5 estados separados a la respuesta |
| GET | `/invoices/{id}/pdf` | **Etapa 6, nuevo** | descarga autenticada (sesion de cliente, org-scoped); 409 si `document_id` todavia no existe |
| GET/POST | `/catalog/items`, `/catalog/items/{id}` (GET/PUT/DELETE) | **Etapa 4, implementado** | CRUD de catalogo (`backend/api/client_catalog_api.py`); `DELETE` es baja logica (`active=false`); busqueda por `q`, paginacion `offset`/`limit` |
| POST | `/invoices/{id}/rectify` | **Etapa 7 (nuevo)** | crea factura rectificativa referenciando la original |
| POST | `/invoices/{id}/cancel` | **Etapa 7 (nuevo)** | registro de anulacion cuando corresponda |
| GET | `/invoices/combined` | **Etapa 10 (nuevo)** | listado unificado `client_app` + `desktop` (desktop solo lectura) |

## 2. `billing_worker` (credencial exclusiva `BILLING_WORKER_API_KEY`, implementado en la Etapa 5)

Desde la Etapa 5, estos endpoints exigen `require_billing_worker_or_internal`
(nunca un token de puesto `g2a3_wks_...`). El worker de escritorio ya no los
llama (seccion 16 del encargo); `invoice_worker` usa en su lugar
`/worker/accounting/*` (ver seccion 3).

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
| POST | `/worker/billing/heartbeat` | **Etapa 5, nuevo**: latido periodico (`worker_heartbeats`) |
| GET | `/worker/notification-health` | entregas `sending`/`unknown` &gt; 30 min (`require_internal_key`) |
| GET | `/worker/heartbeats` | **Etapa 5, nuevo**: ultimo latido de billing_worker/invoice_worker (`require_internal_key`) |
| POST | `/worker/invoice/{id}/fiscal-register` | **Etapa 7 (nuevo)**: `fiscal_registration` |
| POST | `/worker/invoice/{id}/fiscal-cancel` | **Etapa 7 (nuevo)**: `fiscal_cancellation` |

## 3. `invoice_worker` desktop (credencial de puesto, sin cambios de transporte)

| Metodo | Ruta | Job type |
|---|---|---|
| POST | `/worker/customer/claim` | alta Flutter pendiente de tercero/subcuenta |
| POST | `/worker/customer/{id}/confirm` | confirma tercero+subcuenta 430 |
| POST | `/worker/customer/{id}/error` | libera para reintento, registra discrepancia |
| POST | `/worker/customer-sync`, `/worker/series-sync` | snapshot periodico (sin cambios) |
| POST | `/worker/accounting/claim` | **Etapa 3, implementado**: reclama `ClientInvoiceAccountingQueue` (`SELECT FOR UPDATE SKIP LOCKED`) |
| POST | `/worker/accounting/{id}/confirm` | **Etapa 3, implementado**: `create_accounting_export` completado; idempotente |
| POST | `/worker/accounting/{id}/error` | **Etapa 3, implementado**: libera para reintento o marca `review_required`; nunca toca `invoice_status`/`fiscal_status`/`pdf_status`/`delivery_status` |
| POST | `/worker/accounting/heartbeat` | **Etapa 5, nuevo**: latido periodico de `invoice_worker` |
| POST | `/worker/desktop-invoices/sync` | **Etapa 10 (nuevo)**: proyecta cabeceras de facturas desktop |

Las lineas de borrador aceptan `catalog_item_id` opcional: si se indica, el
backend copia descripcion/precio/IVA del articulo a la linea en ese momento
(snapshot); una edicion posterior del articulo nunca altera la linea.

## 4. Reglas de autoria (sin cambios, confirmadas en el codigo)

`organization_id` nunca se acepta del body/payload en los endpoints de
cliente: siempre se deriva de la sesion (`_authenticated_client`). Los
endpoints `/worker/*` nunca aceptan `organization_id` de cliente final; lo
resuelven desde la fila reclamada.
