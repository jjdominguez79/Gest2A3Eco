# Prompt para Codex — Módulo de firma electrónica genérico

> Copia todo el bloque siguiente y pégalo como instrucción inicial a Codex en la raíz del repo.

---

## Tarea

Implementa el módulo de firma electrónica genérico descrito en
`docs/plan_firma_documental_signrequest.md`. **Lee ese documento completo antes de escribir código**;
es la especificación funcional y de arquitectura, y prevalece sobre cualquier suposición tuya.

Objetivo: poder enviar a firma por SignRequest **cualquier PDF** del archivo documental del cliente
o seleccionado desde disco, con seguimiento de estado, descarga de evidencias y archivado
automático del documento firmado. Hoy esa capacidad solo existe dentro del módulo de trámites DGT.

## Antes de empezar

1. Lee `AGENTS.md`, `CLAUDE.md` y `docs/plan_firma_documental_signrequest.md`.
2. Estudia el código que vas a reutilizar, no lo reescribas de cero:
   - `services/signrequest_service.py` (cliente API v1)
   - `services/dgt_remote_integrations.py` (`_BackendClient`, `BackendSignRequestClient`)
   - `services/tramites_dgt_service.py` → `enviar_a_firma`, `actualizar_estado_firma`,
     `anular_ultima_firma`, `_registrar_evidencias_firma`, `_asegurar_etiquetas_firma`
   - `services/gestion_documental_service.py` y `views/ui_gestion_documental.py`
   - `backend/dgt_api/app.py` (endpoints `integrations/signrequest/*`) e `integrations.py`
   - `models/gestor_sqlite.py` (patrón del SCHEMA y de los métodos de acceso)
   - `controllers/app_controller.py` (`_build_module_content`, registro de módulos)
3. Ejecuta `pytest` para tener la línea base verde antes de tocar nada.

## Reglas no negociables

- **No toques** `services/tramites_dgt_service.py`, `views/ui_tramites_dgt.py`,
  `services/tramites_dgt_repository.py` ni `main.py`. El flujo DGT debe seguir funcionando igual.
- Si mueves o reexportas `BackendSignRequestClient`, **mantén el import actual**
  `from services.dgt_remote_integrations import BackendDatapriusClient, BackendSignRequestClient`
  funcionando.
- Convenciones del repo: identificadores, UI y comentarios en español; ficheros fuente en **ASCII
  puro, sin acentos**; disciplina de capas (UI en `views/`, orquestación en `controllers/` y
  `services/`, datos en `models/gestor_sqlite.py`).
- Esquema SQLite: añádelo al SCHEMA embebido con `CREATE TABLE IF NOT EXISTS`, como el resto. Nada
  de migraciones manuales ni de borrar tablas existentes.
- Llamadas de red **siempre** en hilo (`threading.Thread` + `after()`), como ya hace
  `UIGestionDocumental._send_ocr`. La UI no se puede bloquear.
- El token de SignRequest **no** debe viajar al puesto ni aparecer en logs ni en mensajes de error.
  La ruta por defecto es el backend (`dgt_api_url` + `dgt_api_key`).
- No introduzcas dependencias nuevas en `requirements.txt`.

## Entregable por fases

Implementa las fases 0 a 4 del plan. **Haz un commit por fase** con `pytest` en verde antes de pasar
a la siguiente, y resume al final qué quedó en cada una. **No implementes la fase 5** (migración de
DGT y ampliación a facturas/cuotas): es opcional y se decide después.

### Fase 0 — Configuración

- Nuevas claves en `utils/utilidades.py` (con `setdefault` y mapeo de variables de entorno
  `GEST2A3ECO_*`, siguiendo el patrón existente) y en `config.example.json`:
  `firma_habilitada` (True), `firma_permitir_cliente_local` (False), `firma_categoria_firmados`
  ("CONTRATOS"), `firma_max_mb` (15), `firma_webhook_secret` ("").

### Fase 1 — Núcleo

- Tablas `firma_solicitudes`, `firma_firmantes`, `firma_eventos` según el DDL del plan, más sus
  métodos de acceso en `GestorSQLite`.
- `services/firma/provider.py`: `Protocol FirmaProvider` + `build_firma_provider(cfg)` con el orden
  backend → cliente local (solo si `firma_permitir_cliente_local`) → `None`.
- `services/firma/firma_repository.py` y `services/firma/firma_service.py` con la API del plan
  (`crear_solicitud`, `enviar`, `actualizar_estado`, `actualizar_pendientes`, `cancelar`,
  `reenviar`, `listar`).
- `services/firma/etiquetas.py`: extrae ahí `_asegurar_etiquetas_firma` sin dependencias de DGT
  (DGT seguirá usando su copia hasta la fase 5).
- Validaciones obligatorias: PDF, tamaño máximo, todos los firmantes con email, emails distintos
  entre sí, orden correlativo desde 1, teléfono internacional si `usar_sms`, y **el remitente ocupa
  el índice 0 de etiqueta** (si el gestor firma, va primero en la lista de contactos aunque firme el
  último — está documentado en `tramites_dgt_service.py:514`).
- Normalización de estados: `signed|completed → firmado`; `declined → rechazado`;
  `cancelled → cancelado`; `expired → incidencia`; resto → `enviado`; mezcla con alguno firmado →
  `parcialmente_firmado`.
- Tests `tests/test_firma_service.py` y `tests/test_firma_repository.py` con un `FakeProvider`
  (mismo estilo que `tests/test_signrequest_service.py`). Cubre: emails duplicados, firmante sin
  email, fichero no PDF, fichero demasiado grande, cancelar con firma ya completada, idempotencia
  de la descarga de evidencias, archivado del firmado, permisos por rol.

### Fase 2 — Envío desde Gestión documental

- Botón "Enviar a firma" en `views/ui_gestion_documental.py`, habilitado solo con PDF seleccionado.
- `views/ui_firma_dialog.py`: asunto, mensaje, tabla de firmantes con alta desde los terceros de la
  empresa (búsqueda por CIF o nombre, autorrelleno de email y teléfono) y alta manual, orden,
  casilla SMS.
- Columna de estado de firma en el listado documental.

### Fase 3 — Módulo "Firmas"

- `views/ui_firmas.py` + `controllers/ui_firmas_controller.py`; alta del módulo `"firmas"` en
  `controllers/app_controller.py` (`_build_module_content` y `on_open_firmas`), replicando el patrón
  de `gestion_documental`.
- Listado con filtros (estado, fechas, texto) y acciones: actualizar estado, reenviar, cancelar,
  abrir firmado, abrir registro de firma, ver eventos.
- "Nueva solicitud desde disco": archiva primero el PDF en la categoría elegida vía
  `GestionDocumentalService.importar_archivo` y luego crea la solicitud.
- Al pasar a `firmado`: descarga las dos evidencias, las registra en `documentos_archivo` con
  `origen='firma'`, rellena `documento_firmado_archivo_id` y, si hay cliente Dataprius, sube a
  `<empresa>/<ejercicio>/Firmados`. **Cuidado con `UNIQUE(codigo_empresa, hash_archivo)`**: si el
  hash ya existe, vincula al documento existente en lugar de fallar.
- Permisos: enviar, reenviar y cancelar exigen ESCRITURA sobre la empresa
  (`services/secured_gestor.py`); el rol CLIENTE solo consulta.

### Fase 4 — Backend

En `backend/dgt_api`:

- Alias `/api/v1/firma/*` sobre los handlers existentes de `integrations/signrequest/*`,
  **manteniendo las rutas actuales**.
- Nuevo `POST /api/v1/firma/{request_id}/resend` (existe en el cliente local, falta en el backend) y
  su método en `BackendSignRequestClient`.
- `POST /api/v1/firma/webhook` con verificación de secreto compartido, que persiste el evento, y
  `GET /api/v1/firma/eventos?desde=<timestamp>` para que la app lo consulte sin exponerse a Internet.
- En `send`: validar content-type, tamaño máximo y nombre de fichero.
- Ampliar `consultar` para devolver `signers` resumidos (email + estado, **sin URLs**), de forma que
  la UI pueda mostrar "firmado 1 de 2". Respeta el filtro actual que elimina claves terminadas en
  `_url`.

## Criterios de aceptación

1. `pytest` en verde, incluidos los tests DGT existentes sin modificarlos.
2. `python main.py` arranca y el módulo "Firmas" aparece en el panel de empresa.
3. Sin backend configurado, el módulo se muestra deshabilitado con un mensaje claro y **no lanza
   excepciones**.
4. Flujo completo verificable: archivar PDF → enviar a firma → estado `enviado` → actualizar →
   `firmado` → firmado y registro de firma visibles en Gestión documental con su SHA-256.
5. `git diff --stat` no muestra cambios en los ficheros de la lista de "no tocar".
6. Ningún fuente nuevo contiene caracteres no ASCII.

## Al terminar

Entrega un resumen con: commits por fase, ficheros nuevos y modificados, decisiones que tomaste
donde el plan dejaba margen, y una lista de lo que **no** quedó cubierto (fase 5, webhook en
producción, contadores de coste). Si algo del plan resulta inviable al tocar el código, **para,
explica el conflicto y propón alternativa** en lugar de improvisar una solución que rompa las capas.
