# Plan técnico: enviar cualquier documento a firma (SignRequest)

Ampliación del envío a firma electrónica más allá de los trámites DGT: firmar **cualquier PDF**
del archivo documental del cliente o seleccionado desde disco, sin plantilla previa.

- **Arquitectura elegida**: vía backend (`backend/dgt_api`) como pasarela única. El token de
  SignRequest no sale del servidor.
- **Alcance**: archivo documental / subida libre. DGT se mantiene intacto en fase 1-4.
- Este documento es solo planificación. No incluye cambios de código.

---

## 1. Punto de partida

Lo que ya existe y se reutiliza:

| Pieza | Fichero | Estado |
|---|---|---|
| Cliente API v1 local | `services/signrequest_service.py` | Completo y desacoplado (quick-create, consultar, cancelar, reenviar, descargar evidencias con SHA-256) |
| Cliente vía backend | `services/dgt_remote_integrations.py` → `BackendSignRequestClient` | Completo salvo `reenviar` |
| Endpoints backend | `backend/dgt_api/app.py` + `integrations.py` | `status`, `send`, `{id}`, `{id}/cancel`, `{id}/evidence/{tipo}`, todos con `X-API-Key` (`require_internal_key`) |
| Orquestación | `services/tramites_dgt_service.py` (`enviar_a_firma`, `actualizar_estado_firma`, `anular_ultima_firma`, `_registrar_evidencias_firma`, `_asegurar_etiquetas_firma`) | **Acoplada al dominio DGT** |
| Persistencia firma | `dgt_expedientes.firma_estado / firma_request_id / firma_evidencia` (+ tabla `dgt_firmas` en Postgres) | Acoplada a expedientes DGT |
| Archivo documental | `documentos_archivo`, `services/gestion_documental_service.py`, `views/ui_gestion_documental.py` | Completo, con repositorio físico por empresa/ejercicio/categoría |
| Configuración | `signrequest_*` en `utils/utilidades.py` y `config.example.json`; `SIGNREQUEST_*` en `backend/dgt_api/config.py`; `dgt_api_url` / `dgt_api_key` | Completo |

**El problema**: los endpoints del backend ya son genéricos (fichero + firmantes + `external_id`),
pero toda la lógica de negocio de firma (estados, evidencias, archivado, reglas de firmantes) vive
dentro de `TramitesDgtService`, atada a `DOCUMENTOS_BASE` y a los roles vendedor/comprador. Para
firmar un PDF cualquiera hay que **extraer esa lógica a un módulo transversal**.

---

## 2. Arquitectura propuesta

```
views/ui_gestion_documental.py  ──┐
views/ui_firmas.py (nuevo)      ──┼──> controllers/ui_firmas_controller.py
views/ui_firma_dialog.py (nuevo)──┘             │
                                                v
                                   services/firma/firma_service.py   (orquestador genérico)
                                        │             │            │
                     ┌──────────────────┘             │            └──────────────┐
                     v                                v                           v
        services/firma/provider.py          services/firma/            services/gestion_documental_service.py
        (FirmaProvider + factory)           firma_repository.py        (archiva el PDF firmado)
                     │                      (SQLite / API)
                     v
        BackendSignRequestClient  ──>  backend/dgt_api  ──>  SignRequest
        (fallback: SignRequestClient local, desactivado por defecto)
```

Principios:

1. `FirmaService` no conoce DGT, ni facturas, ni gestión documental: recibe una **ruta de fichero +
   lista de firmantes + metadatos** y devuelve una solicitud con estado. El archivado del resultado
   se resuelve con un *callback* o en el controlador, para no crear dependencias circulares.
2. `FirmaProvider` es un `Protocol` con la firma exacta que ya cumplen `SignRequestClient` y
   `BackendSignRequestClient` (`enviar_documento`, `consultar`, `cancelar`, `descargar_evidencias`).
   Añadir un segundo proveedor en el futuro (Box Sign, Viafirma) no toca la UI ni la BD.
3. Capas respetadas según `CLAUDE.md`: UI en `views/`, orquestación en `services/`, datos en
   `models/gestor_sqlite.py`.

---

## 3. Modelo de datos (SQLite, bloque nuevo en `models/gestor_sqlite.py`)

Se sigue el patrón existente `CREATE TABLE IF NOT EXISTS` dentro del SCHEMA, sin migración manual.

```sql
CREATE TABLE IF NOT EXISTS firma_solicitudes (
  id TEXT PRIMARY KEY,                    -- uuid4
  codigo_empresa TEXT NOT NULL,
  ejercicio INTEGER NOT NULL,
  origen TEXT NOT NULL DEFAULT 'archivo', -- archivo | disco | dgt | factura
  documento_archivo_id TEXT,              -- FK documentos_archivo(id), NULL si origen='disco'
  nombre_documento TEXT NOT NULL,
  ruta_origen TEXT NOT NULL,
  hash_origen TEXT NOT NULL,              -- sha256 del PDF enviado
  proveedor TEXT NOT NULL DEFAULT 'signrequest',
  request_id TEXT,                        -- uuid de SignRequest
  external_id TEXT,                       -- "gd:<id>" para correlacionar webhooks
  asunto TEXT, mensaje TEXT,
  usar_sms INTEGER NOT NULL DEFAULT 0,
  callback_url TEXT,
  estado TEXT NOT NULL DEFAULT 'borrador',-- borrador|enviado|parcialmente_firmado|firmado|
                                          -- cancelado|rechazado|incidencia
  ruta_firmado TEXT, ruta_registro_firma TEXT,
  sha256_firmado TEXT, sha256_registro_firma TEXT,
  security_hash TEXT, signing_log_security_hash TEXT,
  documento_firmado_archivo_id TEXT,      -- documentos_archivo del PDF firmado
  creado_por TEXT,
  created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
  enviado_at TEXT, firmado_at TEXT,
  UNIQUE(proveedor, request_id)
);
CREATE INDEX IF NOT EXISTS idx_firma_solicitudes_empresa
  ON firma_solicitudes(codigo_empresa, ejercicio, estado, created_at DESC);

CREATE TABLE IF NOT EXISTS firma_firmantes (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  solicitud_id TEXT NOT NULL,
  orden INTEGER NOT NULL DEFAULT 1,
  nombre TEXT, email TEXT NOT NULL, telefono TEXT,
  rol TEXT,                               -- texto libre: cliente, gestor, avalista...
  tercero_id TEXT,                        -- si se eligió desde terceros
  estado TEXT NOT NULL DEFAULT 'pendiente',
  firmado_at TEXT,
  FOREIGN KEY (solicitud_id) REFERENCES firma_solicitudes(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS firma_eventos (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  solicitud_id TEXT NOT NULL,
  tipo TEXT NOT NULL,                     -- creada|enviada|consultada|firmada|cancelada|error|webhook
  detalle_json TEXT,
  usuario TEXT,
  created_at TEXT NOT NULL,
  FOREIGN KEY (solicitud_id) REFERENCES firma_solicitudes(id) ON DELETE CASCADE
);
```

Notas:

- `firma_eventos` cubre auditoría y sirve de bandeja para los webhooks (fase 4).
- Equivalente Postgres en `models/postgres_migracion.py` y, si el módulo se lleva online,
  `backend/migrations/002_firma.sql`.
- **DGT no se toca**. En fase 5 opcional, `TramitesDgtService` pasa a usar `FirmaService` y
  `dgt_expedientes.firma_*` queda como espejo de solo lectura.

---

## 4. Capa de servicio

### `services/firma/provider.py`

- `class FirmaProvider(Protocol)`: `enviar_documento`, `consultar`, `cancelar`,
  `descargar_evidencias`, `reenviar`.
- `build_firma_provider(cfg) -> FirmaProvider | None`:
  1. Si `dgt_api_url` + `dgt_api_key` → `BackendSignRequestClient` (**ruta por defecto**).
  2. Si `firma_permitir_cliente_local` (nueva clave, `False` por defecto) y hay
     `signrequest_token` → `SignRequestClient`.
  3. Si no → `None`; la UI se muestra deshabilitada con mensaje explicativo (mismo criterio que hoy
     usa `UITramitesDgt`).
- Renombrar conceptualmente: el cliente ya no es "DGT". Mover/reexportar `BackendSignRequestClient`
  a `services/firma/` manteniendo el import antiguo para no romper `ui_tramites_dgt.py`.

### `services/firma/firma_service.py`

API pública:

| Método | Qué hace |
|---|---|
| `crear_solicitud(codigo_empresa, ejercicio, origen, ruta \| documento_archivo_id, firmantes, asunto, mensaje, usar_sms)` | Valida, calcula hash, persiste en estado `borrador`, devuelve `id` |
| `enviar(solicitud_id)` | Llama `provider.enviar_documento` con `external_id = f"gd:{id}"`, guarda `request_id`, estado `enviado`, evento |
| `actualizar_estado(solicitud_id)` | Consulta proveedor, normaliza estado, descarga evidencias si `signed` |
| `actualizar_pendientes(codigo_empresa, ejercicio)` | Refresco masivo al abrir el módulo (en hilo) |
| `cancelar(solicitud_id)` / `reenviar(solicitud_id)` | Con la regla ya probada en DGT: no cancelar si algún firmante completó |
| `listar(filtros)` | Para la vista de firmas |

Normalización de estados (reutilizar la tabla de `actualizar_estado_firma`):
`signed|completed → firmado`; `declined|cancelled|expired → incidencia/cancelado/rechazado`;
resto → `enviado`.

### Validaciones (lecciones ya aprendidas en el módulo DGT)

- Fichero **PDF** obligatorio; si llega `.docx` se convierte antes (`_convertir_pdf` de
  `TramitesDgtService`, a extraer a `utils/`).
- Todos los firmantes con email; **emails distintos entre sí** (SignRequest rechaza duplicados).
- `orden` correlativo desde 1. Si el gestor del despacho firma, va **primero en la lista de
  contactos** aunque firme el último: SignRequest reserva el índice de etiqueta 0 al remitente
  (comentario ya documentado en `tramites_dgt_service.py:514`).
- Teléfono en formato internacional si `usar_sms`.
- Límite de tamaño (proponer 15 MB) y de número de firmantes (proponer 6).

### Zonas de firma

Para PDFs libres no hay etiquetas `[[s|n]]`. Dos modos, configurables por solicitud:

- **Auto** (por defecto): SignRequest coloca la firma; cada firmante la sitúa en el visor.
- **Etiquetas**: solo si el documento procede de una plantilla `.docx` propia. Extraer
  `_asegurar_etiquetas_firma` a `services/firma/etiquetas.py` para reutilizarlo sin arrastrar el
  dominio DGT.

---

## 5. Interfaz

### 5.1 Gestión documental (entrada natural)

En `views/ui_gestion_documental.py`, junto a "Enviar a OCR de facturas":

- Botón **"Enviar a firma"**, habilitado solo si el documento seleccionado es PDF.
- Abre `views/ui_firma_dialog.py`: asunto, mensaje, tabla de firmantes (añadir desde los **terceros
  de la empresa** buscando por CIF/nombre, con autorrelleno de email y teléfono; o alta manual),
  orden, casilla SMS, modo de zona de firma.
- Columna de estado de firma en el listado (`Firmado`, `Pendiente de firma`, `—`).

### 5.2 Nuevo módulo "Firmas"

- Alta en `controllers/app_controller.py`: `_build_module_content` (`modulo == "firmas"`) +
  `on_open_firmas` en el dashboard, siguiendo exactamente el patrón de `gestion_documental`.
- `views/ui_firmas.py`: listado con filtros (estado, fechas, texto) y acciones: *Actualizar estado*,
  *Reenviar*, *Cancelar*, *Abrir documento firmado*, *Abrir registro de firma*, *Ver eventos*.
- Envío también desde aquí con **"Nueva solicitud desde disco"** (`filedialog`), que archiva
  primero el PDF en la categoría elegida y luego crea la solicitud.
- Todas las llamadas de red en `threading.Thread` con actualización vía `after()`, como ya hace
  `UIGestionDocumental`.

### 5.3 Archivado del resultado

Al pasar a `firmado`, `FirmaService` descarga `_firmado.pdf` y `_registro_firma.pdf` y el
controlador los registra en `documentos_archivo` (categoría de origen, o `CONTRATOS` si vino de
disco), con `origen='firma'`, dejando `documento_firmado_archivo_id` apuntando al primero. Si hay
cliente Dataprius configurado, subida a `<empresa>/<ejercicio>/Firmados` reutilizando
`_guardar_documentos_remotos`.

---

## 6. Backend

Cambios en `backend/dgt_api`:

1. **Alias `/api/v1/firma/*`** apuntando a los mismos handlers de `integrations/signrequest/*`
   (el nombre "dgt" ya no describe el ámbito). Mantener las rutas actuales para no romper DGT.
2. **Falta `resend`**: añadir `POST /api/v1/firma/{request_id}/resend` (el cliente local ya lo
   implementa; el backend no).
3. **Webhook**: `POST /api/v1/firma/webhook` como `events_callback_url`, con secreto compartido;
   guarda el evento en BD. La app de escritorio no se expone a Internet: consulta
   `GET /api/v1/firma/eventos?desde=<timestamp>`. Esto elimina el *polling* manual.
4. **Endurecer `send`**: validar `content-type`, tamaño máximo y nombre de fichero.
5. `integrations_status` ya informa de `signrequest`, `firma_gestor_email` y `firma_gestor_telefono`;
   no requiere cambios.

Si el backend no está configurado, el módulo de firmas aparece en modo lectura con el aviso
"Firma electrónica no disponible: configure el backend".

---

## 7. Permisos, configuración y cumplimiento

- Enviar/cancelar exige permiso **ESCRITURA** sobre la empresa (`services/secured_gestor.py`); el
  rol `CLIENTE` solo consulta estado y abre sus documentos firmados.
- `creado_por` en cada solicitud y traza completa en `firma_eventos`.
- Nuevas claves en `utils/utilidades.py` + `config.example.json`:
  `firma_habilitada`, `firma_permitir_cliente_local`, `firma_categoria_firmados`,
  `firma_max_mb`, `firma_webhook_secret`.
- Con backend, **no** distribuir `signrequest_token` en los puestos. Revisar que no aparezca en
  `logs/` ni en los mensajes de error (hoy `_request` vuelca el JSON de error del proveedor).
- RGPD: el PDF sale del despacho hacia SignRequest. Verificar contrato de encargado de tratamiento
  y reflejarlo en el registro de actividades; las evidencias quedan además en local y Dataprius.

---

## 8. Fases

| Fase | Contenido | Estimación |
|---|---|---|
| 0 | Claves de configuración, alias de backend, decisión de proveedor por defecto | 0,5 d |
| 1 | Esquema SQLite + `firma_repository` + `FirmaService` + `provider` + tests con proveedor falso | 1,5 d |
| 2 | Diálogo de envío y botón en Gestión documental (orígenes `archivo` y `disco`) | 1 d |
| 3 | Módulo "Firmas": listado, refresco, cancelar/reenviar, descarga y archivado de evidencias | 1 d |
| 4 | Backend: `resend`, webhook + bandeja de eventos, límites y validaciones | 0,5 d |
| 5 *(opcional)* | Migrar la firma de DGT a `FirmaService`; ampliar a facturas emitidas y cuotas/SEPA | 1-2 d |

Fases 1-3 ya entregan valor completo con *polling* manual; la 4 lo automatiza.

---

## 9. Riesgos y decisiones abiertas

- **Estado por firmante**: `consultar()` devuelve el estado del documento, no de cada firmante. Para
  mostrar "firmado por 1 de 2" hay que leer `signers` del `raw` de SignRequest, que hoy se descarta
  en `SignRequestClient.consultar` y se filtra en el backend (`{k: v for ... if not k.endswith("_url")}`).
  Decisión: ampliar la respuesta con `signers` resumidos (email + estado), sin URLs.
- **Duplicados en el archivo**: `documentos_archivo` tiene `UNIQUE(codigo_empresa, hash_archivo)`. El
  PDF firmado tiene hash distinto al original, pero un reintento de descarga sí colisiona → capturar
  el duplicado y vincular al documento existente en lugar de fallar.
- **Timeouts**: `_BackendClient` usa 90 s y el cliente local 30 s. Con PDFs escaneados grandes hay
  riesgo de corte; limitar tamaño y hacer el envío en hilo con reintento único.
- **Cancelación**: solo si ninguna firma está completada (regla ya implementada en DGT, reutilizarla).
- **Coste**: SignRequest factura por solicitud; abrir la firma a todo el archivo documental puede
  multiplicar el consumo. Conviene un contador por empresa/mes en la vista de firmas.
- **Conversión a PDF**: `_convertir_pdf` depende de Word/LibreOffice en el puesto. Para el flujo de
  subida libre lo razonable es **exigir PDF** y dejar la conversión solo para documentos generados
  por la aplicación.

---

## 10. Pruebas

- `tests/test_firma_service.py` con `FakeProvider`, siguiendo el patrón de
  `tests/test_signrequest_service.py` y `tests/test_tramites_dgt.py`:
  emails duplicados, firmante sin email, fichero no PDF, cancelar con firma completada,
  idempotencia de la descarga de evidencias, archivado del firmado, permisos por rol.
- `tests/test_firma_repository.py`: estados, índices, borrado en cascada.
- Backend: test de `send` con fichero grande y de `webhook` con secreto inválido.
- Smoke manual (añadir a `CONTEXT.md`): archivar un PDF → enviar a firma a un buzón propio → firmar →
  actualizar estado → comprobar que el firmado y el registro aparecen en Gestión documental con su
  SHA-256 y, si procede, en Dataprius.

---

## 11. Ficheros afectados

**Nuevos**

```
services/firma/__init__.py
services/firma/provider.py
services/firma/firma_service.py
services/firma/firma_repository.py
services/firma/etiquetas.py
views/ui_firma_dialog.py
views/ui_firmas.py
controllers/ui_firmas_controller.py
tests/test_firma_service.py
tests/test_firma_repository.py
backend/migrations/002_firma.sql        (solo si el módulo se lleva online)
```

**Modificados**

```
models/gestor_sqlite.py                 esquema + accesos a firma_*
views/ui_gestion_documental.py          botón "Enviar a firma" + columna de estado
controllers/app_controller.py           módulo "firmas" y entrada en el dashboard
utils/utilidades.py                     claves firma_*
config.example.json                     nuevas claves
backend/dgt_api/app.py                  alias /api/v1/firma, resend, webhook, límites
backend/dgt_api/integrations.py         reenviar + signers en consultar
services/dgt_remote_integrations.py     reexport del cliente hacia services/firma
docs/                                   este plan + actualización de README
```

`services/tramites_dgt_service.py` y `views/ui_tramites_dgt.py` **no se tocan** hasta la fase 5.
