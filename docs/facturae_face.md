# Facturae / FACe en Gest2A3Eco

**Estado:** generacion y validacion de Facturae 3.2.2 implementadas.

**Ultima revision contra el codigo:** 2026-08-15.

Gest2A3Eco genera un XML Facturae 3.2.2 desde una factura emitida existente. El
resultado esta preparado para validacion externa y firma posterior; la
aplicacion no lo presenta automaticamente en FACe.

## Flujo

1. Abrir una factura emitida y elegir `Generar Facturae/FACe`.
2. Cargar emisor, receptor, relacion empresa-tercero y lineas de factura.
3. Validar identificacion, direcciones, impuestos, retenciones y totales.
4. Si el receptor es Administracion Publica, validar los centros DIR3.
5. Elegir destino y generar
   `FACTURAE_<NIF_EMISOR>_<NUMERO_FACTURA>.xml`.
6. Guardar ruta, fecha, estado y ultimo error en la factura.

Si hay errores, no se escribe el XML y la interfaz muestra el listado completo.

## Datos obligatorios

Emisor y receptor necesitan nombre o razon social, NIF/CIF/VAT, direccion,
codigo postal, poblacion, provincia y pais. Las lineas deben permitir reconstruir
bases, impuestos, retenciones y total sin descuadres.

Para Administraciones Publicas se requieren:

- oficina contable DIR3;
- organo gestor DIR3;
- unidad tramitadora DIR3;
- opcionalmente organo proponente;
- referencias de expediente, contrato y pedido cuando existan.

## Persistencia

Relacion empresa-tercero:

- `facturae_es_administracion_publica`
- `facturae_dir3_oficina_contable`
- `facturae_dir3_organo_gestor`
- `facturae_dir3_unidad_tramitadora`
- `facturae_dir3_organo_proponente`
- `facturae_referencia_expediente`
- `facturae_referencia_contrato`
- `facturae_referencia_pedido`

Factura emitida:

- `facturae_xml_path`
- `facturae_generated_at`
- `facturae_status`
- `facturae_error`

El campo `pais` de empresa y tercero participa en la construccion de las partes.

## Implementacion

- `services/facturae/facturae_models.py`: contrato del documento.
- `services/facturae/facturae_builder.py`: mapeo y XML 3.2.2.
- `services/facturae/facturae_validator.py`: reglas de validacion.
- `services/facturae/facturae_exporter.py`: orquestacion y datos de persistencia.

Se generan `FileHeader`, `Parties`, `Invoices`, `TaxesOutputs`,
`TaxesWithheld`, `InvoiceTotals`, `Items` y centros administrativos cuando
corresponde. Se contemplan multiples tipos de IVA, IRPF y datos rectificativos.

## Limitaciones

- `sign_facturae_xml()` es un punto de extension y todavia no firma XAdES-EPES.
- No hay envio automatico ni consulta de estado en FACe.
- No se incluye el XSD oficial para validacion local completa.
- Los casos avanzados de facturas rectificativas deben validarse con ejemplos
  reales antes de su presentacion.

Antes de una presentacion real, validar el XML con las herramientas oficiales o
compatibles de Facturae 3.2.2 y firmarlo con un certificado admitido por FACe.

## Pruebas

```powershell
$env:PYTHONPATH = "."
python -m pytest tests/test_facturae_service.py -q
```

Los escenarios cubren factura simple, multiples IVAs, IRPF, DIR3 obligatorio,
descuadre de totales, ausencia de lineas y persistencia de la ruta exportada.
