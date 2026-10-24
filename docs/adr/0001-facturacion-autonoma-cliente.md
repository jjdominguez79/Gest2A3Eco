# ADR 0001: Facturacion autonoma de clientes (Flutter + FastAPI + billing_worker)

**Estado:** aceptado para implementacion por etapas. VeriFactu/AEAT permanece
sin activar hasta completar los requisitos de la seccion 9.

**Fecha:** 2026-10-24.

**Contexto previo:** este ADR continua, no sustituye, `docs/client-platform-pilot.md`
(fase 1: el escritorio publica facturas ya emitidas en el area documental del
cliente, de solo lectura). Esta fase 2 implementa la creacion y emision de
facturas **desde** Flutter, sin depender del escritorio.

## 1. Objetivo

Un cliente debe poder emitir una factura valida desde Flutter de principio a
fin aunque el escritorio, `invoice_worker`, Word, A3ECO, el PostgreSQL interno
o la red del despacho esten caidos o desconectados. El escritorio solo recibe
despues, de forma asincrona, los datos necesarios para la contabilidad.

## 2. Hallazgo clave: que existe ya y que falta

Antes de disenar nada se ha auditado el estado real del repositorio (no el
estado idealizado). La conclusion cambia el alcance del trabajo: **la mayor
parte del dominio ya esta construido**. Lo que falta es, sobre todo,
**desacoplar** un pipeline que hoy esta indebidamente unido.

### 2.1 Ya existe y se reutiliza sin cambios estructurales

| Pieza | Donde | Por que se reutiliza |
|---|---|---|
| Empresa/emisor fiscal | `MessagingOrganization` (`messaging_models.py`) | Ya tiene NIF, razon social, domicilio fiscal y flags `client_*_enabled`. No se crea una segunda entidad de empresa. |
| Cliente/deudor | `ClientInvoiceCustomer` (`client_models.py`) | Unico por `organization_id + tax_id_normalized`, UUID backend estable, ya con columnas `desktop_*` y lease (`desktop_claimed_by/at`, `desktop_lease_expires_at`). |
| Series, borradores, facturas, lineas | `ClientInvoiceSeries`, `ClientInvoice`, `ClientInvoiceLine` | Numeracion atomica ya con `SELECT ... FOR UPDATE` (`client_invoice_service.assign_invoice_number`). Unicidad `organization_id+fiscal_year+series_code+invoice_number`. |
| Snapshot inmutable | `ClientInvoice.issued_snapshot` + `create_issued_snapshot` | JSON determinista generado al emitir; no se recalcula nunca tras la emision. |
| Auditoria con hash | `ClientInvoiceEvent` (`event_hash`, `chain_hash`) | Preparado para encadenamiento; hoy sin uso real (ver 2.2). |
| Outbox con lease | `ClientInvoiceProcessingQueue` | `claimed_by/claimed_at/lease_expires_at`, `retry_count/max_retries`, `SELECT FOR UPDATE SKIP LOCKED` ya en `worker_claim`. |
| Idempotencia de emision | Header `Idempotency-Key` en `POST /drafts/{id}/issue` | Misma clave devuelve la misma factura. |
| Idempotencia de notificaciones | `ClientInvoiceNotificationLog` + `_acquire_notification_lock`/`_complete_notification_lock` | Patron `INSERT ... ON CONFLICT ... RETURNING` con `claim_token`; commit antes de llamar al proveedor externo. Ya hay test de concurrencia real contra Postgres (`tests/test_notification_concurrency_pg.py`). |
| Almacenamiento de PDF | `ClientDocumentStorage` (Azure Blob + fallback local solo test) | Reutilizado sin cambios; el blob ya es el "documento operativo" para `client_invoice`. |
| Feature flags | `feature_flags.py` (`is_invoicing_enabled`/`require_invoicing_enabled`) | AND(flag global en entorno, flag por organizacion). `CLIENT_INVOICING_ENABLED` ya existe y esta en `false`. |
| Patron de worker cloud independiente | `aapp_worker/` (desplegado ya como servicio Railway separado con Playwright/Chromium, ver `deploy/aapp-worker/Dockerfile`) | Es el modelo arquitectonico que sigue `billing_worker` (ver seccion 4). |
| Flutter: modelos, repositorio, 6 pantallas, feature flag de router | `gestinem_app/lib/features/invoicing/**`, `test/invoicing_test.dart` | Ya implementado y testeado; no se reconstruye desde cero (ver ADR seccion 8). |

### 2.2 Gaps reales identificados (lo que esta Etapa corrige)

1. **Bloqueo de emision por escritorio** (seccion 5 del encargo). En
   `client_invoices_api.issue_invoice` (lineas 674-681), emitir falla con 409
   si `customer.pending_desktop_import` es true o falta `desktop_subcuenta`.
   Esto hace que la facturacion dependa del escritorio, exactamente lo que
   se quiere eliminar. **Se retira en la Etapa 3.**

2. **Un unico pipeline para dos responsables distintos.** Hoy
   `ClientInvoiceProcessingQueue` es reclamada por el `invoice_worker` de
   escritorio, que en una sola sesion: reclama -> importa a contabilidad
   (tercero/subcuenta) -> genera el PDF con Word COM
   (`procesos/facturas_word.py`) -> sube el PDF -> publica el documento ->
   envia email -> envia FCM. Es decir: **hoy la emision de PDF/email/FCM
   depende de Word y de que el escritorio este conectado**, lo que contradice
   el objetivo central del encargo. La cola no distingue trabajo fiscal/PDF
   (cloud) de trabajo contable (escritorio). **Se separan en dos outbox
   independientes en la Etapa 3** (ver seccion 5).

3. **Un unico `status` mezclando emision, PDF, email y contabilidad**
   (seccion 8 del encargo). `ClientInvoice.status` usa hoy valores como
   `issued_pending_processing`, `claimed`, `imported`, `rendered`, `emailed`,
   `processing_error` en una sola columna. Un fallo contable no deberia poder
   leerse como un fallo fiscal, y hoy comparten la misma senal. **Se anaden
   columnas de estado separadas en la Etapa 2**, manteniendo `status` sin
   romper compatibilidad.

4. **Veri\*FACTU solo prepara campos.** `compute_verifactu_hash`/
   `chain_verifactu_hash` encadenan siempre contra `""` (cadena vacia) en
   **todas** las facturas, no solo en la primera de la cadena de cada
   obligado tributario. No hay generacion de XML, ni envio, ni adaptador
   AEAT. **Se implementa en la Etapa 7**, con el feature flag de envio
   permanentemente desactivado hasta validacion externa (ver seccion 9).

5. **No existe `billing_worker`.** El render de PDF, el email y el FCM los
   ejecuta hoy el worker de escritorio via Word. No hay ningun proceso cloud
   que los sustituya. **Se crea en la Etapa 5/6.**

6. **No existe catalogo de productos/servicios.** Las lineas de factura se
   escriben siempre a mano. **Se anade en la Etapa 4.**

7. **Asignacion de subcuenta 430 sin bloqueo.**
   `invoice_worker/worker.py::_resolve_subcuenta_430` lee todas las
   subcuentas de la empresa, calcula el maximo en memoria y suma uno, sin
   `SELECT ... FOR UPDATE` ni advisory lock. Bajo concurrencia puede asignar
   la misma subcuenta dos veces. **Se corrige en la Etapa 8**, reutilizando
   el patron `pg_advisory_xact_lock` ya usado en `sync_worker/repository.py`.

8. **No hay listado combinado de facturas desktop + APP en Flutter.** Las
   facturas desktop no tienen una proyeccion de cabecera en el backend (solo
   su PDF se publica como `ClientDocument` con
   `source_system='desktop_invoice'`, fase 1). **Se anade en la Etapa 10.**

## 3. Fuentes de verdad (sin cambios respecto al encargo, confirmadas en el codigo)

- El **backend/PostgreSQL cloud** (`msg_organizations`, `client_invoice_*`)
  es la unica fuente de verdad para: perfil fiscal usado al emitir, clientes
  de facturacion online, catalogo, series APP y su numeracion, borradores,
  facturas emitidas desde Flutter, snapshots, registros Veri\*FACTU, PDF de
  facturas APP, entrega por email/FCM e historico accesible desde Flutter.
- El **PostgreSQL interno del escritorio** (`models/gestor_postgres.py`,
  heredado de `GestorBase`) es la unica fuente de verdad para: `tercero_id`,
  relacion tercero-empresa, subcuenta 430, asiento contable, estado A3ECO y
  `suenlace.dat`.
- **No hay escritura directa entre ambas bases.** Toda comunicacion pasa por
  HTTP autenticado contra el backend (igual que hoy: `invoice_worker` nunca
  abre una conexion SQL al backend, y el backend nunca abre una conexion SQL
  al escritorio). Esto ya se cumple en el codigo actual y se mantiene.
- Los cambios de datos maestros usan revision/version, nunca "ultima
  escritura gana": `ClientInvoiceCustomer` ya versiona por
  `updated_at`/`desktop_sync_status` y registra `desktop_sync_error` en caso
  de discrepancia (ver Etapa 8 para el registro explicito de discrepancias
  fiscales sin sobrescritura silenciosa).

## 4. Decision arquitectonica: `billing_worker` como cliente HTTP, no como proceso con acceso directo a PostgreSQL

El encargo original describe `billing_worker` con acceso directo a
"PostgreSQL del backend". Se **desvia deliberadamente** de esa redaccion
literal por lo siguiente:

- El repositorio ya tiene **un precedente exacto y en produccion**:
  `aapp_worker/`, desplegado como segundo servicio Railway
  (`deploy/aapp-worker/Dockerfile`, con Playwright/Chromium instalado), que
  **no** usa un DSN de PostgreSQL: usa `requests.Session()` con API key de
  rol y los verbos `claim` / `complete` / `fail` contra el backend. El
  backend es quien ejecuta el `SELECT ... FOR UPDATE SKIP LOCKED` real.
- `ClientInvoiceProcessingQueue.worker_claim` **ya implementa** ese mismo
  patron de lease para facturas. No hay que inventar un mecanismo de
  outbox nuevo: hay que separar sus consumidores (ver seccion 5).
- Dar a un proceso cloud publico un DSN completo de PostgreSQL con
  privilegios de escritura amplia aumenta la superficie de ataque sin
  necesidad: el backend ya es el unico punto de verdad y de bloqueo.
- Es coherente con la seccion 3 del encargo ("no implementes escrituras
  directas entre las dos bases de datos... utiliza API, outbox, leases"),
  aplicado tambien a la relacion worker-cloud <-> backend-DB.

`billing_worker` sera, por tanto, un cliente HTTP stateless (como
`aapp_worker`), con su propia API key de rol (`BILLING_WORKER_API_KEY`,
nunca la de escritorio), sin DSN de PostgreSQL en su entorno, sin Tkinter,
sin pywin32, sin Word COM, sin acceso a rutas UNC ni al NAS. El backend sigue
siendo el unico proceso con `BACKEND_DATABASE_URL`.

## 5. Decision arquitectonica: dos outbox independientes, no un pipeline lineal compartido

Se sustituye el pipeline lineal actual (una sola cola reclamada de punta a
punta por un unico worker) por **dos colas independientes**, creadas en la
misma transaccion de emision (outbox transaccional, seccion 9 del encargo):

```
POST /drafts/{id}/issue   (una sola transaccion PostgreSQL)
  |
  +-- asigna numero (SELECT FOR UPDATE sobre ClientInvoiceSeries)
  +-- crea snapshot inmutable
  +-- ClientInvoiceEvent "issued"
  +-- ClientInvoiceProcessingQueue   (NUEVA responsabilidad: SOLO billing_worker)
  |     render_pdf -> publish_document -> send_email -> send_notification
  |     (y mas adelante fiscal_registration/fiscal_cancellation, Etapa 7)
  +-- ClientInvoiceAccountingQueue   (NUEVA tabla: SOLO invoice_worker)
        create_accounting_export (tercero/subcuenta/asiento, sin PDF/email)
```

Ninguna de las dos colas depende de la otra. Un error en
`ClientInvoiceAccountingQueue` solo puede mover `accounting_sync_status`
(ver seccion 6); nunca `fiscal_status`, `pdf_status` ni `delivery_status`.
Un error en `ClientInvoiceProcessingQueue` nunca puede volver
`invoice_status` a `draft` (seccion 15 del encargo).

`invoice_worker` deja de generar PDF, de enviar email/FCM y de encadenar
Veri\*FACTU para facturas APP (seccion 16 del encargo). Mantiene exactamente
lo que ya hace bien: `worker/customer/claim` -> resolver tercero/subcuenta ->
`worker/customer/{id}/confirm`, y pasa a consumir la nueva
`ClientInvoiceAccountingQueue` en vez de la cola compartida.

## 6. Estados separados

Se anaden (Etapa 2, migracion aditiva) 4 columnas nuevas en `client_invoices`
junto a la columna `status` existente, que **se mantiene** por compatibilidad
con clientes Flutter ya desplegados y se sigue escribiendo con sus valores
historicos:

| Columna nueva | Valores | Quien la mueve |
|---|---|---|
| `invoice_status` | `draft`, `issued`, `cancelled`, `rectified` | Emision/anulacion/rectificacion (backend, dentro de la transaccion) |
| `fiscal_status` | `pending`, `processing`, `sent`, `accepted`, `rejected`, `incident` | Motor Veri\*FACTU (Etapa 7) |
| `pdf_status` | `pending`, `processing`, `generated`, `error` | `billing_worker` (render_pdf) |
| `delivery_status` | `pending`, `sending`, `sent`, `skipped`, `error`, `uncertain` | `billing_worker` (send_email/send_notification) |
| `accounting_sync_status` | `pending`, `processing`, `imported`, `review_required`, `error` | `invoice_worker` (create_accounting_export) |

Ejemplo valido final: `invoice_status=issued, fiscal_status=accepted,
pdf_status=generated, delivery_status=sent, accounting_sync_status=pending`.
La API de Flutter devuelve ambos: `status` (legacy) y los 5 campos nuevos;
las pantallas nuevas (Etapa 9) muestran los campos separados.

## 7. Eventos

Se mantiene `ClientInvoiceEvent` como registro inmutable unico (ya con
`event_hash`/`chain_hash`). Tipos de evento normalizados a partir de la
Etapa 3: `draft_created`, `issued`, `fiscal_claimed`, `fiscal_sent`,
`fiscal_accepted`, `fiscal_rejected`, `pdf_generated`, `pdf_error`,
`email_sent`, `email_skipped`, `email_failed`, `fcm_sent`,
`accounting_claimed`, `accounting_imported`, `accounting_review_required`,
`accounting_error`, `cancelled`, `rectified`. El encadenamiendo
`event_hash`/`chain_hash` real para Veri\*FACTU se activa en la Etapa 7 junto
con el motor fiscal (no antes: encadenar sin el motor real seria otra forma
de "preparar campos sin cumplir", que es justo el problema que se corrige).

## 8. Flutter: completar, no reescribir

`gestinem_app/lib/features/invoicing/` ya tiene 6 pantallas, modelos,
repositorio Dio (via `ApiClient`/`apiClientProvider` existente, sin cliente
HTTP nuevo) y tests. El trabajo de la Etapa 9 es, por tanto, de ampliacion
sobre esa base: catalogo de productos/servicios, configuracion de serie y
perfil fiscal, estados separados en la UI, rectificativas, listado combinado
de facturas desktop (solo lectura) y los filtros por ejercicio/serie/cliente/
estado/origen. Se sigue el patron ya validado en `invoicing_screen.dart` /
`subvenciones_screen.dart` (`AsyncValue.when` + `apiErrorMessage` + boton
"Reintentar" + `ref.invalidate`); no existe un widget de estado generico
reutilizable hoy, asi que no se introduce uno nuevo fuera de alcance.

## 9. Veri\*FACTU: alcance, lo implementado y el limite declarado

Implementado en `services/verifactu/` (mismo patron que `services/facturae/`:
`models.py`, `builder.py`, `adapter.py`, `hash.py`, `README.md` con
procedencia documentada):

- **Huella/hash real**, verificada contra el documento oficial AEAT
  "Detalle de las especificaciones tecnicas para generacion de la huella o
  hash de los registros de facturacion" (v0.1.2, 27/08/2024): algoritmo
  SHA-256, orden exacto de campos, formato de concatenacion. Los 3 ejemplos
  oficiales del documento se reproducen byte a byte en
  `tests/test_verifactu_hash.py` (vectores de prueba de oro).
- **Encadenamiento real por organizacion** (= un obligado tributario/SIF en
  este sistema): tabla `client_verifactu_chain_state`, bloqueada con
  `SELECT ... FOR UPDATE` al anadir un registro (mismo patron que
  `assign_invoice_number`), corrigiendo el encadenamiento contra cadena
  vacia de todas las facturas. El registro fiscal inicial (huella + XML) se
  crea dentro de la misma transaccion de emision (seccion 9 del encargo,
  punto 10), en `client_invoice_service.append_verifactu_alta`.
- **XML del registro** (`RegistroAlta`/`RegistroAnulacion`), con nombres de
  elemento y jerarquia transcritos de ejemplos reales del documento oficial
  "Sistemas Informaticos de Facturacion" v1.0.3 (namespaces SOAP/XSD
  incluidos). UTF-8.
- **Rectificativas y anulaciones** (seccion 15): `POST
  .../invoices/{id}/rectify` crea una factura nueva (`TipoFactura=R1`) que
  referencia a la original via `rectifies_invoice_id`; la original pasa a
  `invoice_status=rectified` sin editarse. `POST .../invoices/{id}/cancel`
  genera un `RegistroAnulacion` propio (columnas separadas
  `verifactu_anulacion_hash`/`verifactu_anulacion_xml`: nunca sobrescribe el
  registro de alta original) y marca `invoice_status=cancelled`; es
  idempotente.
- Interfaz `AeatSubmissionPort` aislada y `NullAeatAdapter` (nunca
  transmite, siempre devuelve `incident`, nunca `accepted`) para que el
  resto del sistema sea comprobable sin credenciales reales. Expuesto via
  `POST /worker/invoice/{id}/fiscal-register` (billing_worker, job type
  `fiscal_registration`): mientras `VERIFACTU_SUBMISSION_ENABLED=false` es
  un no-op barato (el backend decide, el worker no necesita el flag).
  `fiscal_cancellation` como job de worker separado no se ha implementado
  todavia: la anulacion calcula su huella/XML de forma sincrona en el mismo
  endpoint de cancelacion (igual que el alta en la emision); el envio real
  de esa anulacion a la AEAT queda pendiente junto con el resto de la
  conexion real.
- Pruebas contractuales de la forma del XML
  (`tests/test_verifactu_builder.py`), del encadenamiento end-to-end
  (`tests/test_verifactu_chain_integration.py`) y de concurrencia real
  contra PostgreSQL (`tests/test_verifactu_chain_concurrency_pg.py`, gated
  por `TEST_POSTGRES_URL`, igual que la numeracion de series).

**Queda expresamente pendiente y sin activar** (feature flag
`VERIFACTU_SUBMISSION_ENABLED=false` permanente hasta que se complete; ver
`services/verifactu/README.md` para el detalle exacto):

- Validacion contra el XSD/contrato oficial completo (`SuministroLR.xsd` /
  `SuministroInformacion.xsd`): no se ha descargado ni incorporado en esta
  sesion.
- El listado oficial completo de codigos `TipoFactura` (lista L2 del anexo
  de la orden): solo se usan `F1` y `R1`, los unicos necesarios aqui.
- Conexion real contra los servicios AEAT (requiere credenciales de entorno
  de pruebas que no estan disponibles en esta sesion) y la firma
  electronica de los registros (documento AEAT aparte, no descargado).
- La posicion exacta del elemento `PrimerRegistro` en el arbol XML: el
  documento oficial confirma su existencia y semantica por texto, pero el
  diagrama correspondiente no se pudo renderizar en esta sesion; se ha
  implementado como alternativa directa a `RegistroAnterior` dentro de
  `Encadenamiento`, que es la lectura mas directa del texto disponible.

No se declara en ningun documento que Veri\*FACTU este "completo" ni
"certificado" mientras lo anterior siga pendiente, conforme exige el
encargo. Lo que SI se declara, con evidencia verificable (vectores de
prueba oficiales reproducidos exactamente), es que el algoritmo de huella y
el encadenamiento ya no son el placeholder contra cadena vacia que existia
antes de esta etapa.

## 10. Railway: dos servicios

| Servicio | Comando | Dockerfile |
|---|---|---|
| `backend` (ya existe) | `uvicorn backend.api.app:app --host 0.0.0.0 --port $PORT --proxy-headers` | `backend/Dockerfile` |
| `billing-worker` (nuevo) | `python -m billing_worker` | `deploy/billing-worker/Dockerfile` (mismo patron que `deploy/aapp-worker/Dockerfile`: Playwright + Chromium) |

Variables compartidas: `BACKEND_PUBLIC_BASE_URL`. Variables exclusivas del
worker: `BILLING_WORKER_API_KEY_FILE` (secreto por archivo, igual que
`AAPP_WORKER_API_KEY_FILE`), `BILLING_WORKER_POLL_INTERVAL_SECONDS`,
`BILLING_WORKER_LEASE_MINUTES`, `BILLING_WORKER_ID`. El worker no expone
puerto ni API publica. Reinicio: `restartPolicyType = "ON_FAILURE"`. Apagado
sin perder trabajos: `SIGTERM`/`SIGINT` marcan `stop_event`; el trabajo en
curso termina su commit o lo libera via `/worker/invoice/{id}/error`, nunca
se mata a mitad de una subida de PDF sin que la cola quede en estado
`claimed` con lease (que caduca y se reclama de nuevo). Detalle completo en
`docs/billing_worker.md` (Etapa 5).

## 11. Estrategia de migracion

Todas las migraciones son SQL plano en `backend/migrations/`, con
`CREATE TABLE IF NOT EXISTS` / `ADD COLUMN IF NOT EXISTS`, descubiertas por
orden lexicografico por `backend/migrate.py` (no hay que registrarlas en
ninguna lista; `BASELINE_FILES` es un conjunto cerrado historico que no se
toca). No se elimina ninguna columna existente en esta fase. Numeracion
reservada para este trabajo: `042` en adelante, una migracion por etapa que
la necesite.

## 12. Riesgo aceptado y documentado

- El cambio de autenticacion en los endpoinds `/worker/*` de facturas (de
  `require_workstation_or_internal` a una credencial exclusiva de
  `billing_worker`) es seguro de introducir ahora porque
  `CLIENT_INVOICING_ENABLED` sigue en `false` en produccion (fase 2 no
  lanzada): no hay trafico real de escritorio dependiendo de ese contrato
  todavia.
- Mantener `status` en paralelo a los 5 campos separados es deuda tecnica
  deliberada y temporal: se retira en una fase posterior fuera de este
  encargo, cuando todos los consumidores (incluida la app ya publicada)
  dejen de leer el campo legacy.

## 13. Etapa 8: invoice_worker refactorizado y subcuenta 430 atomica

`invoice_worker/worker.py` pierde toda responsabilidad sobre PDF, email,
FCM y Veri\*FACTU para facturas APP (ya eran responsabilidad de
billing_worker desde las Etapas 5-7; esta etapa retira el codigo que
todavia las ejecutaba): se eliminan `PdfRenderer`/`RealPdfRenderer` y los
metodos `_render_pdf`/`_upload_pdf`/`_publish_document`/`_request_email`/
`_request_fcm`. Su unico trabajo pasa a ser: reclamar altas de cliente
(`/worker/customer/claim`, sin cambios) y reclamar facturas de la cola
contable independiente (`/worker/accounting/claim`, Etapa 3) para importar
tercero + subcuenta + factura a `facturas_emitidas_docs`.

Como `/worker/invoice/{id}/payload` paso a ser exclusivo de billing_worker
en la Etapa 5, `/worker/accounting/claim` ahora devuelve el payload
completo en su respuesta (`_build_invoice_payload`, compartida con
`worker_get_payload`) para que `invoice_worker` no necesite esa ruta.
`invoice_worker/__main__.py --dry-run` usa el nuevo
`GET /worker/accounting/auth-check` (no mutante) para verificar su
credencial, en vez del endpoint de billing_worker que ya rechazaria su
token. `WorkerConfig` pierde `word_template_dir`/`pdf_output_dir`/
`sender_mailbox` (sin uso); `install.ps1` deja de exigir Word/plantilla.

`procesos/facturas_word.py` y el flujo de facturas creadas por el
escritorio (Tkinter) **no se tocan**: siguen usando Word COM exactamente
igual que antes. Solo se retira Word del circuito APP, conforme al encargo
("no elimines Word COM globalmente si sigue siendo necesario para facturas
creadas por el escritorio").

**Idempotencia de la importacion** (seccion 16 del encargo): el id interno
de `facturas_emitidas_docs` es deterministico (`flutter_<uuid-backend>`) y
`upsert_factura_emitida` ya usaba `ON CONFLICT(id) DO UPDATE`; reprocesar el
mismo evento nunca duplica la fila. Se evalua anadir columnas dedicadas
`source_system`/`accounting_sync_revision` a esa tabla para reporting
desktop mas rico, pero se deja fuera de esta etapa: es un cambio de esquema
sobre una tabla central del escritorio (A3ECO, `suenlace.dat`, Facturae,
area cliente) que no se puede validar en este entorno de trabajo sin una
base PostgreSQL real ni la suite completa del escritorio (Windows); el
prefijo `flutter_` ya permite filtrar el origen (`WHERE id LIKE
'flutter_%'`) mientras tanto.

**Asignacion atomica de subcuenta 430** (seccion 17 del encargo):
`_resolve_subcuenta_430` ahora:

1. Adquiere `pg_advisory_xact_lock(hashtext('subcuenta430:' || codigo_empresa))`
   (nuevo `GestorPostgres.advisory_lock_empresa_430`, especifico de
   PostgreSQL, mismo patron que `sync_worker/repository.py` para los
   buzones de correo) antes de leer el maximo existente, para minimizar
   colisiones en el caso comun.
2. La garantia final es la restriccion `UNIQUE(codigo_empresa, subcuenta)`
   que **ya existia** en `maestro_subcuentas_empresa` (verificado en el
   esquema, `models/gestor_base.py`): si, aun con el lock, dos procesos
   coincidieran, el `INSERT` que pierde la carrera falla y el metodo
   reintenta hasta 3 veces recalculando el siguiente numero libre.
3. Nunca reutiliza la subcuenta de otro tercero (comprueba `nif_snapshot`
   antes de asignar una nueva).

Pruebas (`tests/test_invoice_worker.py`, `tests/test_gestor_postgres.py`):
reintento ante conflicto simulado, agotamiento de reintentos, no
reutilizacion de subcuenta ajena, idempotencia de la importacion por UUID
backend, verificacion de que el advisory lock usa una clave por empresa, y
un test estatico que impide que vuelvan a filtrarse metodos de PDF/email/
FCM o imports de Word/pywin32 a `invoice_worker`.
