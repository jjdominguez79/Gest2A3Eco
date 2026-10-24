# billing_worker

Worker cloud independiente para el pipeline fiscal/PDF/entrega de facturas
emitidas desde Flutter. Ver `docs/adr/0001-facturacion-autonoma-cliente.md`.

## Que hace

Reclama trabajo de `ClientInvoiceProcessingQueue` via
`POST /worker/claim` (el backend otorga el lease con
`SELECT ... FOR UPDATE SKIP LOCKED`) y, por factura reclamada:

1. Renderiza el PDF (`billing_worker/handlers/render_pdf.py`).
2. Lo sube (`POST /worker/invoice/{id}/pdf`).
3. Publica el documento en el area del cliente (`publish-document`).
4. Dispara el envio por email (`send-email`, idempotente server-side).
5. Dispara la notificacion FCM (`send-fcm`, best-effort: su fallo nunca
   hace fallar el trabajo).

Cada paso comprueba el estado actual antes de repetirlo (idempotencia por
tipo de trabajo): si el worker se reinicia a mitad de la secuencia, el
siguiente intento reanuda en el paso que falte.

## Que NO hace

- No expone ninguna API publica ni puerto HTTP.
- No abre ninguna conexion SQL (ni al backend ni, mucho menos, al
  PostgreSQL interno del escritorio). Todo pasa por
  `billing_worker/backend_client.py`.
- No importa Tkinter, pywin32, `win32com` ni `comtypes` (verificado por
  `tests/test_billing_worker.py::test_billing_worker_package_never_imports_windows_or_desktop_postgres_modules`).
- No depende de `invoice_worker` ni de que el escritorio este conectado.

## Arranque

```
python -m billing_worker
```

## Variables de entorno

| Variable | Obligatoria | Descripcion |
|---|---|---|
| `BILLING_WORKER_BACKEND_URL` | si | URL publica del backend (sin barra final) |
| `BILLING_WORKER_API_KEY_FILE` | si | Ruta a un archivo con la credencial exclusiva de billing_worker (secreto Railway/Docker, nunca inline) |
| `BILLING_WORKER_ID` | no | Identificador de instancia; por defecto `hostname-<random>` |
| `BILLING_WORKER_POLL_INTERVAL_SECONDS` | no | Espera entre sondeos cuando no hay trabajo (defecto 15) |
| `BILLING_WORKER_LEASE_MINUTES` | no | Duracion del lease solicitado al reclamar (defecto 10, maximo 60) |
| `BILLING_WORKER_REQUEST_TIMEOUT_SECONDS` | no | Timeout HTTP por llamada (defecto 60) |
| `BILLING_WORKER_HEARTBEAT_INTERVAL_SECONDS` | no | Frecuencia minima del heartbeat (defecto 60) |
| `BILLING_WORKER_MAX_BACKOFF_SECONDS` | no | Techo del backoff exponencial tras errores consecutivos de `claim()` (defecto 300) |

Variable compartida con el backend: `BACKEND_PUBLIC_BASE_URL` no se usa aqui
directamente; `BILLING_WORKER_BACKEND_URL` apunta a esa misma URL publica.

## Secreto requerido en el backend

`BILLING_WORKER_API_KEY` en el backend (Railway), distinto de
`BACKEND_INTERNAL_API_KEY` y de cualquier token de puesto de escritorio.
Ver `backend/api/security.py::require_billing_worker_or_internal`: nunca
acepta un token `g2a3_wks_...`.

## Heartbeat y observabilidad

Cada ciclo (como maximo cada `BILLING_WORKER_HEARTBEAT_INTERVAL_SECONDS`)
el worker llama a `POST /worker/billing/heartbeat`. El backend guarda una
sola fila por worker (`worker_heartbeats.billing_worker`) con el ultimo
`instance_id` visto, contadores acumulados y `last_seen_at`. Consulta
(solo `BACKEND_INTERNAL_API_KEY`):

```
GET /api/v1/messaging/client/invoicing/worker/heartbeats
```

## Apagado sin perder trabajo

`SIGTERM`/`SIGINT` marcan `stop_event`. El trabajo en curso (la secuencia de
llamadas de un unico `_process`) siempre termina antes de que el bucle
vuelva a comprobar la senal: nunca se interrumpe a mitad de una subida de
PDF. Si el proceso se mata de forma abrupta (`SIGKILL`, caida del
contenedor) a mitad de un trabajo, el `lease_expires_at` de ese trabajo
caduca en el backend (minutos, segun `BILLING_WORKER_LEASE_MINUTES`) y
cualquier instancia (la misma u otra) lo reclama de nuevo con
`SKIP LOCKED`; cada paso ya ejecutado se detecta por idempotencia y no se
repite.

## Recuperacion de trabajos abandonados

No requiere intervencion manual: el lease caduca solo. Para forzar una
revision manual de trabajos con muchos reintentos, usar
`GET /worker/notification-health` (email/FCM) y la columna `retry_count`/
`max_retries` de `client_invoice_processing_queue`.

## Escalado y concurrencia

Puede ejecutarse con varias replicas Railway sin duplicar trabajo: el
backend es quien otorga el lease (`SELECT FOR UPDATE SKIP LOCKED`), no el
worker. Ver `tests/test_invoice_numbering_concurrency_pg.py` y
`tests/test_worker_endpoints.py` para la prueba del lado del backend, y
`tests/test_billing_worker.py::test_two_worker_instances_sharing_the_backend_never_duplicate_a_claim`
para el contrato del lado del worker.

## Despliegue Railway

Servicio nuevo e independiente del backend web, mismo repositorio:

- Build: `deploy/billing-worker/Dockerfile` (ver `railway.billing-worker.toml`).
- Start: `python -m billing_worker`.
- Sin `healthcheckPath` (no expone HTTP); Railway supervisa por codigo de
  salida y `restartPolicyType = "ON_FAILURE"`.
- Rebuild solo cuando cambia `billing_worker/**` o `deploy/billing-worker/**`
  (`watchPatterns`).

### Rollback

`railway redeploy <commit-anterior>` sobre el servicio `billing-worker`. No
hay esquema propio que revertir: el worker no posee ninguna tabla: toda su
persistencia es la del backend.

## Pendiente (Etapa 6 y siguientes)

- `render_pdf.py` es todavia un placeholder sin Chromium (Etapa 6 lo
  sustituye por el renderer real HTML/CSS + Playwright + QR fiscal).
- `fiscal_registration`/`fiscal_cancellation` (Etapa 7): el worker todavia
  no envia nada a la AEAT; ver `docs/adr/0001-facturacion-autonoma-cliente.md`
  seccion 9 para el alcance declarado de Veri*FACTU.
