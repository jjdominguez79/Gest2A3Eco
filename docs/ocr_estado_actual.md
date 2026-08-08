# Estado actual del modulo OCR

El OCR de facturas recibidas tiene un unico nucleo activo:

- `services/ocr/ocr_service.py`: orquestador con persistencia.
- `services/ocr/base.py`: contrato comun de motores.
- `services/ocr/engines/`: motores `pdf_text`, `tesseract` y `azure`.
- `services/ocr/invoice_interpreter.py`: interpretacion de texto libre a `OcrInvoiceResult`.
- `services/ocr_contabilidad_service.py`: proyeccion de una factura OCR validada al flujo contable.
- `views/ui_facturas_recibidas_ocr.py`: pantalla principal de captura y revision.

La ruta legacy basada en `services/ocr_service.py`, `services/ocr_provider.py`,
`services/ocr_parser_service.py`, `views/ui_ocr_facturas.py` y
`views/ui_ocr_detalle.py` ha sido retirada.

## Modelo de datos

Las tablas tipadas son la fuente principal del OCR:

- `documentos_ocr`
- `facturas_recibidas_ocr`
- `facturas_recibidas_ocr_lineas_iva`
- `facturas_recibidas_ocr_retenciones`
- `ocr_correcciones`

`facturas_recibidas_docs` se conserva como proyeccion contable porque
Contabilidad y la generacion de `suenlace.dat` todavia consumen ese contrato.
No debe volver a usarse como modelo OCR primario.

## Configuracion

La configuracion activa del motor es:

- `ocr_motor_activo`
- `azure_doc_intelligence_endpoint`
- `azure_doc_intelligence_key`
- `azure_doc_intelligence_model_id`

Las claves legacy `ocr_endpoint`, `ocr_provider` y `mindee_api_key` no forman
parte del flujo OCR activo.
