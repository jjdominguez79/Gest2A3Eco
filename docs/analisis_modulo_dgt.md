# Analisis modulo Trámites DGT

## 1. Arquitectura actual relevante

- Punto de entrada: `main.py` inicializa Tkinter, configura rutas, abre `GestorSQLite`, autentica y lanza `AppController`.
- Panel inicial: `views/ui_panel_general.py` muestra empresas accesibles y acciones globales.
- Navegacion: `controllers/app_controller.py` decide entre panel global, dashboard de empresa y modulos internos.
- Autenticacion: `services/auth_service.py` construye `UserSession` desde tablas `usuarios` y `usuarios_empresas`.
- Roles y permisos: `admin`, `empleado`, `cliente`; los permisos existentes son por empresa. Se añade permiso global `tramites_dgt`.
- Persistencia SQLite: `models/gestor_sqlite.py` contiene esquema, migraciones idempotentes y repositorios.
- Generacion documental: `procesos/facturas_word.py` usa `docxtpl`, `python-docx` y conversion a PDF via `win32com`.
- Envio: `services/email_service.py` abre Outlook o envia por SMTP. WhatsApp se abre via URL en el modulo de emitidas.

## 2. Elementos reutilizables

- Validacion y normalizacion de identificaciones en `utils/validaciones.py`.
- Rutas de datos de aplicacion en `utils/utilidades.py`.
- Servicio de email Outlook/SMTP en `services/email_service.py`.
- Patron de migraciones SQLite idempotentes de `GestorSQLite`.
- Registro de JSON de generacion documental, ya usado por el modulo documental legacy.
- Generacion Word/PDF existente, preparada para adaptarse a plantillas DGT.

## 3. Elementos obsoletos

- Tablas legacy `plantillas_documentos`, `intervinientes`, `operaciones`, `operacion_intervinientes`, `documentos_generados` y `documento_intervinientes` permanecen fuera de la interfaz activa.
- Metodos legacy bajo el bloque `LEGACY DOCUMENTAL` no se eliminan porque pueden existir bases antiguas y no hay evidencia suficiente de que no se consulten por scripts externos.
- El autoescaneo documental antiguo no aparece como flujo activo.

## 4. Elementos que no deben modificarse

- Flujos contables por empresa.
- Facturacion emitida/recibida y OCR.
- Tablas documentales legacy existentes en bases SQLite.
- Configuracion de plantillas Word globales actual.
- Permisos por empresa ya existentes.

## 5. Riesgos

- Las bases de datos reales pueden contener datos legacy no visibles en la UI.
- La futura firma electronica requiere contrato estable con proveedor externo.
- Los enlaces seguros necesitan una superficie web o handler de protocolo para formularios externos; esta entrega deja tokens y URLs preparados.
- La generacion final DOCX/PDF DGT necesitara plantillas legales definitivas.

## 6. Plan de implantacion

1. Crear permiso global `tramites_dgt`.
2. Crear tablas DGT separadas y no vinculadas a empresa.
3. Añadir servicio `TramitesDgtService`.
4. Añadir vista global accesible desde el panel inicial.
5. Permitir crear expediente minimo, regenerar enlaces, enviar por email/WhatsApp, validar y generar documentos preliminares.
6. Sustituir documentos `.txt` por plantillas DOCX/PDF cuando existan modelos definitivos.
7. Incorporar integracion de firma mediante `firma_provider` y `firma_request_id`.

## 7. Archivos creados

- `services/tramites_dgt_service.py`
- `views/ui_tramites_dgt.py`
- `tests/test_tramites_dgt.py`
- `docs/analisis_modulo_dgt.md`

## 8. Archivos modificados

- `models/auth.py`
- `services/auth_service.py`
- `services/secured_gestor.py`
- `models/gestor_sqlite.py`
- `controllers/app_controller.py`
- `views/ui_panel_general.py`

## 9. Archivos que podrian eliminarse

Ninguno en esta fase. La eliminacion del bloque documental legacy queda pendiente de una comprobacion funcional con bases reales y scripts de explotacion externos.

## 10. Compatibilidad con bases existentes

- No se elimina ni altera destructivamente ninguna tabla antigua.
- Las nuevas tablas se crean con `CREATE TABLE IF NOT EXISTS`.
- Los campos nuevos se incorporan sin migraciones destructivas.
- Los documentos DGT usan tablas propias: `dgt_expedientes` y `dgt_documentos_generados`.
