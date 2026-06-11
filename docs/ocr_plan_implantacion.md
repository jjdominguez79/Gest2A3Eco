# Plan de implantacion del modulo OCR — Gest2A3Eco

**Fecha:** 2026-06-09  
**Estado:** En desarrollo activo

---

## Vision del modulo

Modulo de captura documental que permite importar facturas recibidas en PDF
o imagen, extraer automaticamente los datos fiscales, revisarlos, validarlos
y generar el fichero `suenlace.dat` para A3ECO, con trazabilidad completa
de las correcciones manuales.

---

## Arquitectura objetivo

```
Archivo (PDF / imagen)
    │
    ▼
services/ocr/
    ├── OcrService                  ← orquestador con BD
    │   ├── _construir_cadena_motores()
    │   │   ├── PdfTextEngine      ← pymupdf/pypdf (texto nativo)
    │   │   ├── AzureInvoiceEngine ← Azure prebuilt-invoice
    │   │   └── LocalOcrEngine     ← Tesseract local
    │   └── _ejecutar_motores()
    │
    ├── InvoiceInterpreter          ← extraccion de campos con regex
    │
    └── types.py                    ← OcrInvoiceResult, OcrVatLine, etc.
        │
        ▼
models/gestor_sqlite.py
    ├── documentos_ocr              ← hash, motor, estado, texto
    ├── facturas_recibidas_ocr      ← datos de factura propuesta
    ├── facturas_recibidas_ocr_lineas_iva
    ├── facturas_recibidas_ocr_retenciones
    └── ocr_correcciones            ← auditoria de cambios manuales
        │
        ▼
views/ui_facturas_recibidas_ocr.py  ← panel unificado lista + editor
    │
    ▼
services/ocr_recibidas_service.py   ← generacion suenlace.dat
    │
    ▼
procesos/facturas_recibidas.py      ← registros A3ECO tipo 1/2 + 9 + 6
```

---

## Fases completadas

### Fase 1 — OCR basico funcional (anterior a 2026-06-09)
- [x] `OCRService.procesar_factura()` con pypdf
- [x] `OcrParserService` con regex (NIF, fecha, total, IVA multi-base)
- [x] Bandejas de estado en `ui_ocr_facturas.py`
- [x] Generacion suenlace.dat desde documentos OCR
- [x] Tabla `facturas_recibidas_docs` y `ocr_lineas_fiscales`

### Fase 2 — Enriquecimiento de datos (anterior a 2026-06-09)
- [x] Tabla `captura_documental_retenciones`
- [x] Tabla `maestro_subcuentas_empresa`
- [x] Dialog de detalle `ui_ocr_detalle.py`
- [x] Resolucion de terceros por NIF

### Fase 3 — Modulo OCR tipado (2026-06-09)
- [x] Contrato tipado `OcrInvoiceResult` en `services/ocr/types.py`
- [x] Interfaz abstracta `OcrEngineBase` en `services/ocr/base.py`
- [x] Motor PDF texto: `services/ocr/engines/pdf_text_engine.py`
- [x] Motor local Tesseract: `services/ocr/engines/local_engine.py`
- [x] Esqueleto Azure: `services/ocr/engines/azure_invoice_engine.py`
- [x] `InvoiceInterpreter` con reglas completas en `services/ocr/invoice_interpreter.py`
- [x] `OcrService` con hash, duplicados y persistencia en nuevas tablas
- [x] Tablas: `documentos_ocr`, `facturas_recibidas_ocr`, lineas IVA, retenciones, correcciones
- [x] Vista unificada `views/ui_facturas_recibidas_ocr.py`
- [x] Documentacion: `docs/ocr_estado_actual.md`, `docs/ocr_azure.md`

---

## Fases pendientes

### Fase 4 — Mejoras de extraccion (proxima)

**Objetivo:** Aumentar la tasa de extraccion correcta sin motor externo.

Tareas:
- [ ] Detectar nombre de empresa emisora por patrones de cabecera de factura
- [ ] Deteccion de numero de factura con serie (A-001, FAC/2024/001)
- [ ] Soporte a facturas con tabla de articulos (extraer lineas de detalle)
- [ ] Normalizacion de NIFs: validacion de digito de control
- [ ] Deteccion de moneda (EUR, USD, GBP)
- [ ] Tests unitarios para `InvoiceInterpreter` con 20+ casos reales

### Fase 5 — Tesseract operativo

**Objetivo:** Procesar PDFs escaneados e imagenes sin motor externo de pago.

Tareas:
- [ ] Instalar Tesseract OCR en el equipo de produccion
- [ ] Instalar paquete de idioma espanol (`spa`)
- [ ] Validar extraccion en facturas escaneadas tipo
- [ ] Mejorar preprocesado de imagen (contraste, binarizacion)
- [ ] Incluir `pytesseract` en `requirements.txt`

### Fase 6 — Azure Document Intelligence activo

**Objetivo:** Extraccion estructurada para facturas complejas.

Tareas:
- [ ] Configurar recurso Azure en portal.azure.com
- [ ] Añadir `azure-ai-documentintelligence` a `requirements.txt`
- [ ] Probar con muestra de 50 facturas reales
- [ ] Afinar mapeo de campos (ver `docs/ocr_azure.md`)
- [ ] Implementar tabla `ocr_configuracion` para credenciales en BD
- [ ] UI para configurar endpoint/key desde la app

### Fase 7 — Aprendizaje y mejora continua

**Objetivo:** La app aprende de las correcciones del usuario.

Tareas:
- [ ] Analizar `ocr_correcciones` para detectar patrones frecuentes
- [ ] Sugerir nombre y NIF de proveedor en base a facturas previas del mismo emisor
- [ ] Autocompletar cuentas contables desde historial de uso
- [ ] Dashboard de metricas OCR (tasa de exito por motor, campos mas corregidos)

---

## Criterios de aceptacion del modulo OCR

| Criterio | Estado |
|---|---|
| La app arranca con `python main.py` sin errores | ✓ |
| Se puede abrir una empresa y entrar al modulo OCR | ✓ |
| Se puede importar un PDF con texto | ✓ |
| Si el PDF tiene texto, se extraen datos basicos | ✓ |
| Se crea `documento_ocr` y `factura_recibida_ocr` | ✓ |
| El usuario puede corregir cabecera, IVA y retenciones | ✓ |
| La factura puede validarse si cuadra total y tiene NIF/numero | ✓ |
| No se rompe el flujo existente de plantillas ni emitidas | ✓ |
| Se generan logs de errores con contexto | ✓ |
| La generacion de suenlace.dat sigue funcionando | ✓ |
| Los duplicados (mismo hash) se detectan | ✓ |
| Hay un log de correcciones manuales (auditoria) | ✓ |

---

## Riesgos y mitigaciones

| Riesgo | Probabilidad | Impacto | Mitigacion |
|---|---|---|---|
| PDFs escaneados sin texto (imagenes) | Alta | Alto | Tesseract o Azure en Fase 5/6 |
| Facturas con formato no estandar | Media | Medio | Revision manual siempre disponible |
| Cambios en el formato de Azure SDK | Baja | Medio | Motor aislado en `azure_invoice_engine.py` |
| Degradacion del flujo suenlace existente | Baja | Muy alto | No se modifica `ocr_recibidas_service.py` ni `facturas_recibidas.py` |
| Acumulacion de documentos sin procesar | Media | Bajo | Bandeja "Errores" y boton reprocesar |

---

## Notas de integracion con A3ECO

- El campo `id` del documento OCR se incluye en el registro tipo 6 del suenlace
  como referencia de trazabilidad (`pdf_ref`).
- El flujo existente (`facturas_recibidas_docs` → `generar_recibidas_suenlace`)
  se mantiene intacto.
- Las nuevas tablas (`documentos_ocr`, `facturas_recibidas_ocr`) son adicionales
  y no reemplazan las existentes hasta que la migracion este completa.
- La migracion de datos existentes de `facturas_recibidas_docs` a
  `documentos_ocr` se planifica para Fase 4.
