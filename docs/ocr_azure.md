# Azure Document Intelligence en Gest2A3Eco

**Estado:** activo a traves del backend cuando `ocr_motor_activo` es `azure`.

**Ultima revision contra el codigo:** 2026-08-15.

## Arquitectura vigente

```text
Escritorio
  |-- integrations_api_url
  |-- WorkstationToken
  `-- POST /api/v1/ocr/invoices/analyze
         -> Backend FastAPI / Railway
              |-- AZURE_DOC_INTELLIGENCE_ENDPOINT
              |-- AZURE_DOC_INTELLIGENCE_KEY
              `-- AZURE_DOC_INTELLIGENCE_MODEL_ID
```

La clave Azure se mantiene en Railway. El escritorio envia el documento y el ID
de modelo, y recibe un `OcrInvoiceResult` normalizado. No recibe ni persiste la
clave del proveedor.

El modo Azure directo se conserva solo para instalaciones sin
`integrations_api_url`. En ese caso, endpoint y clave se obtienen de la
configuracion/entorno seguro del puesto y se usa `AzureInvoiceEngine`.

## Configuracion

Escritorio, sin secretos:

```json
{
  "ocr_motor_activo": "azure",
  "azure_doc_intelligence_model_id": "facturas-produccion-v1",
  "integrations_api_url": "https://gest2a3eco-production.up.railway.app"
}
```

Backend:

```text
AZURE_DOC_INTELLIGENCE_ENDPOINT=https://mi-recurso.cognitiveservices.azure.com/
AZURE_DOC_INTELLIGENCE_KEY=<secreto-en-Railway>
AZURE_DOC_INTELLIGENCE_MODEL_ID=facturas-produccion-v1
```

El endpoint devuelve `503` si Azure no esta configurado, `401` si falta una
credencial valida y `415` para tipos de archivo no admitidos.

## Orden y errores

Si Azure esta seleccionado y hay backend, `BackendOcrEngine` es prioritario. Su
resultado, incluido un error de configuracion o de modelo, se devuelve al
usuario para que el problema sea visible. No se sustituye silenciosamente por
la interpretacion local de PDF.

Sin backend, Azure local puede ejecutarse antes que los motores de texto. En
configuraciones no Azure, `PdfTextEngine` procesa primero los PDF con texto y
`LocalOcrEngine` usa Tesseract cuando esta instalado.

## Campos normalizados

| Campo Azure | Campo Gest2A3Eco | Notas |
|---|---|---|
| `VendorName` | `proveedor_nombre` | Razon social del emisor |
| `VendorTaxId` | `proveedor_nif` | NIF/CIF/VAT del emisor |
| `InvoiceId` | `numero_factura` | Serie y numero |
| `InvoiceDate` | `fecha_factura` | Fecha ISO |
| `DueDate` | `fecha_vencimiento` | Fecha ISO |
| `InvoiceTotal` | `total` | Total con impuestos |
| `SubTotal` | `base_total` | Base imponible total |
| `TotalTax` | `iva_total` | Cuota total de IVA |
| `TaxDetails` | `bases_iva` | Desglose fiscal si Azure lo identifica |
| confianza | `confianza` | Valor normalizado entre 0 y 1 |

El motor tambien reconoce los nombres del modelo personalizado:
`ProveedorNif`, `ProveedorNombre`, `NumeroFactura`, `FechaFactura`,
`BaseTotal`, `IvaTotal`, `TotalFactura` y `LineasIva`.

## Modelo personalizado y aprendizaje

Las correcciones hechas en la aplicacion se auditan, pero no reentrenan Azure
automaticamente. Cuando una factura se valida,
`services/ocr/aprendizaje_service.py` puede registrar una copia privada y sus
datos estructurados en `ocr_aprendizaje_ejemplos`. El conjunto puede exportarse
a un contenedor Blob de entrenamiento configurado mediante:

```text
AZURE_OCR_TRAINING_CONNECTION_STRING
AZURE_OCR_TRAINING_CONTAINER
```

El entrenamiento sigue realizandose en Azure Document Intelligence Studio:

1. preparar una muestra diversa de documentos ya revisados;
2. etiquetar los campos acordados;
3. entrenar y validar con una muestra de control separada;
4. publicar el nuevo ID en Railway y en la configuracion no sensible del
   escritorio;
5. conservar el modelo anterior para rollback.

## Limitaciones y operacion

- Azure puede no desglosar correctamente todas las bases de IVA o retenciones;
  la revision manual sigue siendo obligatoria.
- El modelo puede confundir el NIF del cliente con el emisor; el normalizador y
  las reglas de cabecera reducen ese riesgo, pero no lo eliminan.
- Los importes y fechas aceptan formatos europeos e internacionales antes de
  normalizarse.
- Nunca se deben registrar claves, connection strings ni documentos completos
  en logs de error.

Los precios y cuotas de Azure cambian con el tiempo; deben consultarse en la
pagina oficial antes de estimar costes, no mantenerse como una cifra fija en
esta documentacion.
