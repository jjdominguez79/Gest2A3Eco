# Integracion Azure Document Intelligence — Gest2A3Eco

**Estado:** Esqueleto preparado, no activo por defecto.  
**Motor:** `services/ocr/engines/azure_invoice_engine.py`

---

## 1. Que es Azure Document Intelligence

Azure Document Intelligence (antes Form Recognizer) es un servicio de Microsoft
que analiza documentos de forma estructurada.  El modelo **prebuilt-invoice**
extrae directamente los campos de una factura (proveedor, NIF, numero, fecha,
importes, impuestos) sin necesidad de configurar reglas de extraccion.

Ventajas frente al OCR local (Tesseract):
- Funciona con PDFs escaneados e imagenes de baja calidad.
- Devuelve campos estructurados (no texto libre).
- Soporta facturas en multiple idiomas.
- Devuelve nivel de confianza por campo.

---

## 2. Requisitos

### Azure
1. Crear un recurso **Document Intelligence** en Azure Portal (plan Free F0 disponible).
2. Anotar el **Endpoint** y la **Clave de API** del recurso.

### Python
```bash
pip install azure-ai-documentintelligence
```

Agregar al `requirements.txt`:
```
azure-ai-documentintelligence
```

---

## 3. Configuracion

### Opcion A: config.json / config.local.json
```json
{
  "ocr_motor_activo": "azure",
  "azure_doc_intelligence_endpoint": "https://mi-recurso.cognitiveservices.azure.com/",
  "azure_doc_intelligence_key": "tu_clave_de_api_aqui"
}
```

### Opcion B: Base de datos (futuro)
Pendiente implementar tabla `ocr_configuracion` para guardar credenciales cifradas.

**IMPORTANTE:** No incluir claves de API en el control de versiones.  
Usar `config.local.json` (excluido del repo via `.gitignore`).

---

## 4. Activacion del motor

El motor se activa automaticamente si:
1. `ocr_motor_activo = "azure"` esta configurado.
2. El SDK `azure-ai-documentintelligence` esta instalado.
3. Endpoint y clave son validos.

La cadena de motores en `OcrService` tiene este orden:
```
1. PdfTextEngine   (PDF con texto nativo — siempre primero, gratuito)
2. AzureInvoiceEngine  (si configurado)
3. LocalOcrEngine  (Tesseract — si instalado)
```

Si el PDF tiene texto, Azure no se invoca (economia de llamadas API).

---

## 5. Mapeo de campos Azure → OcrInvoiceResult

| Campo Azure (prebuilt-invoice) | Campo OcrInvoiceResult | Notas |
|---|---|---|
| `VendorName` | `proveedor_nombre` | Nombre del emisor |
| `VendorTaxId` | `proveedor_nif` | CIF/NIF/VAT del emisor |
| `InvoiceId` | `numero_factura` | Numero de la factura |
| `InvoiceDate` | `fecha_factura` | Fecha de emision (ISO) |
| `DueDate` | `fecha_vencimiento` | Fecha de vencimiento |
| `InvoiceTotal` | `total` | Total a pagar (con IVA) |
| `SubTotal` | `base_total` | Base imponible total |
| `TotalTax` | `iva_total` | Suma de cuotas de IVA |
| `TaxDetails[].Amount` | `bases_iva[].cuota_iva` | Desglose por tipo IVA |
| `Items[]` | (futuro) | Lineas de detalle de factura |
| confidence de campos | `confianza` | Media de confianzas de campos clave |

### Limitaciones conocidas
- Azure no siempre desglosa la base imponible por tipo de IVA; en ese caso
  se usa la base total con un tipo inferido.
- El numero de factura puede incluir prefijos de serie; revisar manualmente.
- Para facturas en castellano, el modelo puede confundir "Retenciones" con IVA.

---

## 6. Costes Azure

| Plan | Llamadas/mes | Precio adicional |
|---|---|---|
| Free (F0) | 500 | Gratuito |
| Standard (S0) | Ilimitado | ~1,50 €/1.000 paginas |

Referencia: https://azure.microsoft.com/es-es/pricing/details/ai-document-intelligence/

---

## 7. Ejemplo de codigo (ya implementado en azure_invoice_engine.py)

```python
from services.ocr.engines.azure_invoice_engine import AzureInvoiceEngine

engine = AzureInvoiceEngine(
    endpoint="https://mi-recurso.cognitiveservices.azure.com/",
    api_key="mi_clave",
)
if engine.disponible():
    result = engine.extraer(Path("factura.pdf"))
    print(result.proveedor_nif, result.total)
```

---

## 8. Seguridad

- Las claves de API se almacenan en `config.local.json` (no versionado).
- En produccion, considerar Azure Key Vault o variables de entorno.
- No loguear la api_key en ningun registro de log.
- El motor nunca expone la clave fuera de la llamada HTTP.
