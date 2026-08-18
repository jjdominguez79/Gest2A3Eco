# Estado actual del modulo OCR

**Estado:** operativo.

**Ultima revision contra el codigo:** 2026-08-18.

## Flujo funcional

```text
PDF o imagen, seleccionado o arrastrado
  -> eleccion: factura de proveedor o factura de cliente
  -> bandeja Procesando mientras trabaja el motor
  -> OcrService: archivo, hash y deteccion de duplicados
  -> motor OCR configurado
  -> factura OCR propuesta
  -> revision manual de cabecera, IVA y retenciones
  -> validacion y proyeccion a Contabilidad
  -> generacion de suenlace.dat desde Contabilidad
```

La pantalla OCR no genera directamente `suenlace.dat`. Una factura validada se
proyecta al contrato contable de recibidas o emitidas y la exportacion A3 se
realiza despues desde Contabilidad. Las facturas emitidas creadas por el propio
programa conservan su circuito directo y no pasan por OCR; el flujo OCR de
emitidas sirve para documentos externos entregados por el cliente.

## Componentes activos

- `services/ocr/ocr_service.py`: archivo en repositorio compartido,
  orquestacion, duplicados y persistencia.
- `services/ocr/base.py` y `services/ocr/types.py`: contratos tipados.
- `services/ocr/engines/backend_ocr_engine.py`: OCR Azure delegado al backend.
- `services/ocr/engines/pdf_text_engine.py`: extraccion de texto nativo.
- `services/ocr/engines/local_engine.py`: Tesseract opcional.
- `services/ocr/invoice_interpreter.py`: interpretacion heuristica de texto.
- `services/ocr_contabilidad_service.py`: proyeccion contable de recibidas.
- `services/ocr_emitidas_contabilidad_service.py`: proyeccion de emitidas
  externas al modulo de Contabilidad.
- `services/ocr/aprendizaje_service.py`: ejemplos validados y exportacion privada
  a Azure Blob para entrenamiento.
- `views/ui_facturas_recibidas_ocr.py`: captura, revision y validacion.

La antigua ruta `services/ocr_service.py`, `services/ocr_provider.py`,
`views/ui_ocr_facturas.py` y `views/ui_ocr_detalle.py` esta retirada.

## Seleccion de motores

Con `integrations_api_url` configurada, el escritorio usa primero
`BackendOcrEngine` y se autentica con
`WorkstationToken`. Azure se ejecuta en Railway y su clave nunca llega al
puesto. Un error del backend se muestra al usuario; no se oculta con
un resultado heuristico local.

Sin URL o credencial de backend, la cadena local solo usa texto PDF y despues
Tesseract cuando esta disponible. El acceso directo a Azure desde el escritorio
esta retirado.

## Modelo de datos

Las tablas tipadas son la fuente principal:

- `documentos_ocr`
- `facturas_recibidas_ocr`
- `facturas_recibidas_ocr_lineas_iva`
- `facturas_recibidas_ocr_retenciones`
- `facturas_emitidas_ocr`
- `facturas_emitidas_ocr_lineas_iva`
- `facturas_emitidas_ocr_retenciones`
- `ocr_correcciones`
- `ocr_aprendizaje_ejemplos`

El contrato normalizado conserva por separado emisor/proveedor y
destinatario/cliente. En una factura emitida se utiliza el destinatario para
evitar asignar por error la propia empresa emisora como cliente contable.
La clasificacion elegida queda bloqueada durante el procesamiento. Si un mismo
archivo se habia clasificado al reves y sigue pendiente de revision, se
reclasifica y reprocesa; nunca se cambia automaticamente si ya entro en
Contabilidad.

`facturas_recibidas_docs` y `facturas_emitidas_docs` son las proyecciones
consumidas por Contabilidad y por el generador A3. No deben utilizarse como
modelo OCR primario.

## Configuracion

El escritorio solo necesita `integrations_api_url` y un `WorkstationToken`.
Endpoint, clave e ID del modelo Azure se configuran exclusivamente en Railway.

Credenciales:

- `WorkstationToken` en Credential Manager para el backend;
- `AZURE_DOC_INTELLIGENCE_KEY` en Railway.

Las claves `ocr_endpoint`, `ocr_provider` y `mindee_api_key` no forman parte del
flujo activo.
