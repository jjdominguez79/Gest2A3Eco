# Estado actual del modulo OCR

**Estado:** operativo.

**Ultima revision contra el codigo:** 2026-08-15.

## Flujo funcional

```text
PDF o imagen
  -> OcrService: archivo, hash y deteccion de duplicados
  -> motor OCR configurado
  -> factura OCR propuesta
  -> revision manual de cabecera, IVA y retenciones
  -> validacion y proyeccion a Contabilidad
  -> generacion de suenlace.dat desde Contabilidad
```

La pantalla OCR no genera directamente `suenlace.dat`. Una factura validada se
proyecta mediante `services/ocr_contabilidad_service.py` al contrato contable
`facturas_recibidas_docs`; la exportacion A3 se realiza despues desde
Contabilidad.

## Componentes activos

- `services/ocr/ocr_service.py`: archivo en repositorio compartido,
  orquestacion, duplicados y persistencia.
- `services/ocr/base.py` y `services/ocr/types.py`: contratos tipados.
- `services/ocr/engines/backend_ocr_engine.py`: OCR Azure delegado al backend.
- `services/ocr/engines/azure_invoice_engine.py`: Azure directo solo en modo
  local sin backend.
- `services/ocr/engines/pdf_text_engine.py`: extraccion de texto nativo.
- `services/ocr/engines/local_engine.py`: Tesseract opcional.
- `services/ocr/invoice_interpreter.py`: interpretacion heuristica de texto.
- `services/ocr_contabilidad_service.py`: proyeccion contable.
- `services/ocr/aprendizaje_service.py`: ejemplos validados y exportacion privada
  a Azure Blob para entrenamiento.
- `views/ui_facturas_recibidas_ocr.py`: captura, revision y validacion.

La antigua ruta `services/ocr_service.py`, `services/ocr_provider.py`,
`views/ui_ocr_facturas.py` y `views/ui_ocr_detalle.py` esta retirada.

## Seleccion de motores

Con `ocr_motor_activo = "azure"` y `integrations_api_url` configurada, el
escritorio usa primero `BackendOcrEngine` y se autentica con
`WorkstationToken`. Azure se ejecuta en Railway y su clave nunca llega al
puesto. Un error del motor seleccionado se muestra al usuario; no se oculta con
un resultado heuristico local.

Sin URL de backend, el modo de compatibilidad puede usar
`AzureInvoiceEngine` con una clave guardada en Credential Manager o aportada por
entorno. Si Azure no esta seleccionado, la cadena local usa texto PDF y despues
Tesseract cuando esta disponible.

## Modelo de datos

Las tablas tipadas son la fuente principal:

- `documentos_ocr`
- `facturas_recibidas_ocr`
- `facturas_recibidas_ocr_lineas_iva`
- `facturas_recibidas_ocr_retenciones`
- `ocr_correcciones`
- `ocr_aprendizaje_ejemplos`

`facturas_recibidas_docs` es la proyeccion consumida por Contabilidad y por el
generador A3. No debe volver a utilizarse como modelo OCR primario.

## Configuracion

Valores no sensibles del escritorio:

- `ocr_motor_activo`
- `azure_doc_intelligence_endpoint` (solo modo Azure local)
- `azure_doc_intelligence_model_id`
- `integrations_api_url`

Credenciales:

- `WorkstationToken` en Credential Manager para el backend;
- `AZURE_DOC_INTELLIGENCE_KEY` en Railway;
- clave Azure local en Credential Manager solo para instalaciones sin backend.

Las claves `ocr_endpoint`, `ocr_provider` y `mindee_api_key` no forman parte del
flujo activo.
