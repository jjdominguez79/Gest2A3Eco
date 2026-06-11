# Estado actual del modulo OCR — Gest2A3Eco

**Fecha de auditoria:** 2026-06-09  
**Rama analizada:** `ocr`

---

## 1. Archivos existentes relacionados con OCR/Documentos/Facturas recibidas

### Servicios (`services/`)

| Archivo | Lineas | Proposito |
|---|---|---|
| `services/ocr_service.py` | ~100 | Orquestador OCR publico. Punto de entrada: `OCRService.procesar_factura(file_path) -> dict` |
| `services/ocr_provider.py` | ~290 | Abstraccion de proveedores OCR: `OCRProviderLocal` (pypdf), `OCRProviderHTTP`, `OCRProviderTesseract`, `OCRProviderMindee`. Fabrica `build_provider_chain()` |
| `services/ocr_parser_service.py` | ~390 | Parser texto libre → campos. `OcrParserService.parsear_y_validar(texto)` → `ParseResult` con NIF, fecha, total, lineas IVA multi-base |
| `services/ocr_recibidas_service.py` | ~160 | Integracion OCR → suenlace.dat. `generate_suenlace_for_docs()`, `doc_to_rows()`, `mark_docs_as_generated()` |
| `services/terceros_ocr_service.py` | ~80 | Resolucion de terceros (maestro) desde datos OCR por NIF |

### Controladores (`controllers/`)

| Archivo | Proposito |
|---|---|
| `controllers/ui_ocr_facturas_controller.py` | Orquestador principal del flujo OCR: carga documentos, lanza thread OCR, gestiona bandejas, valida, genera suenlace |
| `controllers/ui_ocr_detalle_controller.py` | Edicion/revision de un documento OCR concreto |

### Vistas (`views/`)

| Archivo | Proposito |
|---|---|
| `views/ui_ocr_facturas.py` | Bandejas OCR (Procesando / Errores / Pte.revision / Pte.contabilizar / Contabilizadas). Notebook con Treeview por estado |
| `views/ui_ocr_detalle.py` | Dialogo modal de detalle: visor PDF, edicion cabecera, tabla IVA editable, retenciones |

### Procesos A3ECO (`procesos/`)

| Archivo | Proposito |
|---|---|
| `procesos/facturas_recibidas.py` | Generacion de registros tipo 1/2 + 9 + 6 para suenlace.dat desde filas de facturas recibidas |

### Modelos (`models/`)

| Archivo | Tablas OCR relevantes |
|---|---|
| `models/gestor_sqlite.py` | `facturas_recibidas_docs`, `ocr_lineas_fiscales`, `asientos_contables`, `captura_documental_retenciones` |
| `models/facturas_common.py` | Renderizadores A3ECO: `render_a3_tipo12_cabecera()`, `render_a3_tipo9_detalle()`, `render_a3_tipo6_id()` |

### Requirements relevantes

```
pymupdf      # fitz — renderizado PDF a imagen, extraccion texto
pypdf        # PdfReader — extraccion texto nativo PDF (alternativa)
pillow       # Procesamiento imagenes
requests     # HTTP para proveedores OCR externos
```

---

## 2. Que hace cada componente

### `services/ocr_service.py` (OCRService)
- Detecta tipo de fuente (pdf / imagen).
- Ejecuta cadena de proveedores: local pypdf → HTTP configurable.
- Delega parsing a `OcrParserService`.
- Devuelve dict legacy compatible con `facturas_recibidas_docs`.

### `services/ocr_provider.py`
- Define `OCRResult(texto, confianza, proveedor, errores, campos_raw)`.
- `OCRProviderLocal`: extrae texto nativo con `pypdf.PdfReader` (solo PDFs digitales).
- `OCRProviderHTTP`: POST a endpoint externo configurable.
- `OCRProviderTesseract`: OCR via pytesseract (requiere Tesseract instalado).
- `OCRProviderMindee`: API Mindee (requiere api_key).

### `services/ocr_parser_service.py` (OcrParserService)
- Extrae NIF/CIF, nombre proveedor, numero factura, fecha, total.
- Detecta lineas IVA multiples via tabla (`21%  1000  210`) y pares explicitos.
- Genera `ParseResult.bandeja = "error" | "pendiente_revision"`.
- Metodo `to_legacy_dict()` mantiene compatibilidad con el controlador.

### `services/ocr_recibidas_service.py`
- `resolve_recibidas_template()`: carga plantilla de recibidas (cuentas por defecto).
- `build_terceros_by_nif()`: indexa maestro de terceros por NIF.
- `doc_to_rows()`: expande un doc OCR a filas (una por tramo IVA).
- `generate_suenlace_for_docs()`: coordina todo y llama a `generar_recibidas_suenlace()`.
- `mark_docs_as_generated()`: marca documentos como contabilizados.

### `controllers/ui_ocr_facturas_controller.py`
- Gestiona el flujo completo: importar → OCR thread → bandejas → validar → suenlace.
- `_build_pending_doc()`: crea estructura inicial del documento.
- `_merge_ocr_result()`: combina doc original con resultado del parser.
- `_validate_para_contabilizar()`: NIF, numero, fecha y total != 0.

### `views/ui_ocr_facturas.py`
- 5 bandejas (Notebook): Procesando, Errores, Pte.revision, Pte.contabilizar, Contabilizadas.
- Toolbar por bandeja con acciones contextuales.
- `set_bandeja_docs(estado, docs)`: actualiza Treeview con datos de BD.

### `views/ui_ocr_detalle.py`
- Dialogo modal (Toplevel).
- Visor del documento PDF (si disponible).
- Formulario de cabecera editable.
- Tabla de lineas IVA editable.
- Bloque de retencion.
- Botones: Guardar / Validar / Anterior-Siguiente doc.

---

## 3. Partes aprovechables

| Componente | Valoracion | Motivo |
|---|---|---|
| `services/ocr_provider.py` | ★★★★★ CONSERVAR | Abstraccion solida, extension punto claro, sin dependencias de UI |
| `services/ocr_parser_service.py` | ★★★★☆ CONSERVAR | Buen parsing multi-base IVA, funciones puras testeables |
| `services/ocr_recibidas_service.py` | ★★★★★ CONSERVAR | Unico conector OCR → suenlace, maduro y funcional |
| `procesos/facturas_recibidas.py` | ★★★★★ CONSERVAR | Renderizadores A3ECO correctos, no tocar |
| `models/facturas_common.py` | ★★★★★ CONSERVAR | Fuente de verdad del formato A3ECO |
| `views/ui_ocr_facturas.py` | ★★★★☆ CONSERVAR | Bandejas funcionales, mejorar visor |
| `views/ui_ocr_detalle.py` | ★★★☆☆ MEJORAR | Funcional pero sin sincronizacion con nuevas tablas |
| `controllers/ui_ocr_facturas_controller.py` | ★★★★☆ CONSERVAR | Logica de flujo correcta, extender sin romper |
| `services/ocr_service.py` | ★★★☆☆ REFACTORIZAR | Devuelve dict legacy; migrar a OcrInvoiceResult |

---

## 4. Partes a retirar o refactorizar

| Componente | Accion | Motivo |
|---|---|---|
| `OCRService.procesar_factura()` devuelve dict | Refactorizar gradualmente | Reemplazar por `OcrInvoiceResult` tipado sin romper el controlador existente |
| `ParseResult.to_legacy_dict()` | Mantener temporalmente | Compatibilidad hasta que el controlador consuma `OcrInvoiceResult` directamente |
| `OCRProviderMindee` | Revisar | Dependencia de SDK de terceros; migrar al patron `OcrEngineBase` nuevo |
| Columna `lineas_json` en `facturas_recibidas_docs` | Mantener + migrar | Datos duplicados vs tabla `ocr_lineas_fiscales`; priorizar tabla estructurada |

No se elimina codigo por ahora. Las partes obsoletas se documentan aqui.

---

## 5. Que falta para un flujo OCR operativo completo

### Critico (bloqueante)
- [x] Motor de extraccion de texto PDF nativo (pypdf/pymupdf) → **YA EXISTE**
- [x] Parser de campos (NIF, fecha, total, IVA) → **YA EXISTE**
- [x] Flujo de bandejas y validacion → **YA EXISTE**
- [x] Generacion suenlace.dat → **YA EXISTE**
- [x] Tablas SQLite tipadas con hash y motor → **NUEVAS: Fase 3**
- [x] Contrato tipado OcrInvoiceResult → **NUEVO: services/ocr/types.py**

### Importante (no bloqueante)
- [ ] Tesseract para PDFs escaneados → `services/ocr/engines/local_engine.py` (listo, requiere instalacion)
- [ ] Azure Document Intelligence → `services/ocr/engines/azure_invoice_engine.py` (esqueleto listo)
- [ ] Visor de PDF integrado en la UI → requiere tkinter + pymupdf render
- [ ] Deteccion de retenciones IRPF en el parser → mejorar `ocr_parser_service.py`
- [ ] Validacion de NIF con digito de control → `utils/validaciones.py`

### Mejoras futuras
- [ ] Aprendizaje por correcciones (tabla `ocr_correcciones`)
- [ ] Importacion masiva de carpeta de facturas
- [ ] Notificaciones por email de facturas procesadas
- [ ] Exportacion al SII (Suministro Inmediato de Informacion)

---

## 6. Conexion con empresas, terceros, plan contable y suenlace

```
Empresa (empresas.digitos_plan, ejercicio)
  └─> OcrService — usa empresa_id para aislar documentos por empresa

Terceros (terceros + terceros_empresas)
  └─> TercerosOcrService.resolver_tercero(nif) → subcuenta_proveedor
  └─> build_terceros_by_nif() indexa maestro para suenlace

Plan contable (plan_cuentas)
  └─> _resolver_cuenta_proveedor() en procesos/facturas_recibidas.py
  └─> Prefijo 400 + NIF → subcuenta 8 digitos ajustada a digitos_plan

Suenlace.dat
  └─> generar_recibidas_suenlace() en procesos/facturas_recibidas.py
  └─> Registros tipo 1/2 (cabecera) + tipo 9 (lineas IVA) + tipo 6 (trazabilidad OCR)
  └─> Codificacion: latin-1, CRLF
```

---

## 7. Tablas SQLite relevantes

### Tablas existentes (sistema anterior)
- `facturas_recibidas_docs` — documento OCR principal
- `ocr_lineas_fiscales` — lineas de IVA por documento
- `captura_documental_retenciones` — retenciones IRPF
- `asientos_contables` — asientos generados

### Tablas nuevas (Fase 3)
- `documentos_ocr` — registro con hash, motor, confianza global
- `facturas_recibidas_ocr` — datos de factura propuesta por OCR
- `facturas_recibidas_ocr_lineas_iva` — lineas IVA del nuevo modulo
- `facturas_recibidas_ocr_retenciones` — retenciones del nuevo modulo
- `ocr_correcciones` — log de correcciones manuales por campo y usuario
