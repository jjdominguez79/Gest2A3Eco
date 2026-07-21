# Analisis modulo Trámites DGT

## 1. Arquitectura actual relevante

- Punto de entrada: `main.py` inicializa Tkinter, configura rutas, abre `GestorSQLite`, autentica y lanza `AppController`.
- Panel inicial: `views/ui_panel_general.py` muestra empresas accesibles y acciones globales.
- Navegacion: `controllers/app_controller.py` decide entre panel global, dashboard de empresa y modulos internos.
- Autenticacion: `services/auth_service.py` construye `UserSession` desde tablas `usuarios` y `usuarios_empresas`.
- Roles y permisos: `admin`, `empleado`, `cliente`; los permisos existentes son por empresa. Se añade permiso global `tramites_dgt`, gestionable desde Administracion de usuarios.
- Persistencia SQLite: `models/gestor_sqlite.py` contiene esquema, migraciones idempotentes y repositorios.
- Acceso a datos DGT: `services/tramites_dgt_repository.py` separa el servicio del almacenamiento concreto para permitir una futura API online.
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
6. Capturar y revisar datos completos de vendedor/comprador desde la vista interna.
7. Registrar documentacion aportada con ruta y hash SHA-256.
8. Verificar tokens de enlace para una futura interfaz externa de captura.
9. Generar DOCX desde plantillas DGT si existen, o DOCX basico como respaldo.
10. Intentar PDF cuando el entorno disponga de conversion Word COM.
11. Preparar paquete de firma mediante `firma_provider` y `firma_request_id`.
12. Mantener las plantillas DGT en carpeta editable de usuario para poder cambiarlas sin nuevo codigo ni version.
13. Abrir un formulario de captura para vendedor/comprador a partir del enlace tokenizado.

## 7. Archivos creados

- `services/tramites_dgt_service.py`
- `views/ui_tramites_dgt.py`
- `views/ui_tramites_dgt_public.py`
- `tests/test_tramites_dgt.py`
- `docs/analisis_modulo_dgt.md`

## Estado implantado

- Gestinem puede crear expedientes globales DGT sin empresa contable asociada.
- Los enlaces de vendedor y comprador se regeneran con token seguro y se guardan solo como hash.
- La vista permite editar datos completos de vendedor y comprador.
- La vista permite adjuntar documentacion y registrar su SHA-256.
- La validacion exige datos minimos de partes, identificacion valida, direccion y documentacion.
- La generacion crea contrato/mandatos en TXT y DOCX, conserva el JSON de generacion e intenta PDF si el equipo lo permite.
- La firma queda marcada como `preparado` con el listado de documentos, pendiente de conectar Box Sign, SignRequest u otro proveedor.
- Queda preparada la verificacion de token para conectar un formulario externo o handler de protocolo.
- Las plantillas se buscan en `word_templates_dir/tramites_dgt` y pueden crearse/abrirse desde la UI, por lo que su contenido se modifica fuera del codigo.
- El enlace seguro puede abrir un formulario local de captura que verifica referencia, rol y token antes de guardar datos o adjuntos.
- Administracion de usuarios permite conceder o retirar el permiso global `tramites_dgt` a empleados autorizados.
- `TramitesDgtService` depende de `DgtRepository`, no de SQLite directamente; el adaptador actual es `SQLiteDgtRepository`.

## Preparacion online

La siguiente migracion hacia portal web/base online debe implementar un repositorio alternativo, por ejemplo `ApiDgtRepository`, con la misma interfaz que `DgtRepository`. La UI interna y el servicio de negocio podran seguir usando los mismos metodos mientras el almacenamiento real pasa a una API con PostgreSQL y almacenamiento documental externo.

## Plantillas editables

La carpeta editable esperada es la configurada en `word_templates_dir`, subcarpeta `tramites_dgt`.

Archivos:

- `dgt_contrato_compraventa.docx`
- `dgt_mandato_comprador.docx`
- `dgt_mandato_vendedor.docx`

La aplicacion puede crear plantillas base si faltan. Desde ese momento basta con editar los `.docx` en Word y volver a generar documentos; no hace falta publicar una nueva version.

## Captura por enlace

El formulario `UITramitesDgtPublicForm` permite reutilizar la logica de enlaces seguros sin exponer el panel interno. Recibe `referencia`, `rol` y `token`, verifica el hash guardado en SQLite y solo entonces permite guardar datos o adjuntar documentacion.

La UI interna incluye un boton `Formulario` junto a cada enlace para probar el flujo. Cuando el protocolo `gest2a3eco://` quede registrado en instalador/SO, el mismo formulario puede abrirse desde el enlace enviado por email o WhatsApp.

## Protocolo de sistema

El instalador registra `gest2a3eco://` en Windows. Al abrir un enlace DGT, el ejecutable recibe la URL como argumento, abre la base configurada y muestra directamente `UITramitesDgtPublicForm` si el token es valido. No se muestra login para este flujo, porque la autorizacion queda limitada por el token del expediente.

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
