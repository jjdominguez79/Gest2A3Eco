# Facturae / FACe en Gest2A3Eco

Gest2A3Eco permite generar, desde una factura emitida existente, un fichero XML Facturae 3.2.2 preparado para validacion estructural y uso posterior en FACe/MiFacturae.

## Que hace

- Anade la accion `Generar Facturae/FACe` en la pantalla de facturas emitidas.
- Valida datos obligatorios de emisor, receptor, lineas, impuestos, retenciones y totales.
- Genera un XML Facturae 3.2.2 con `FileHeader`, `Parties`, `Invoices`, `TaxesOutputs`, `TaxesWithheld`, `InvoiceTotals` e `Items`.
- Guarda en la factura la ruta del XML, fecha de generacion, estado Facturae y ultimo error de validacion.

## Datos necesarios

### Emisor

- Nombre o razon social.
- CIF/NIF.
- Direccion.
- Codigo postal.
- Poblacion.
- Provincia.
- Pais.

### Cliente / receptor

- Nombre o razon social.
- CIF/NIF.
- Direccion.
- Codigo postal.
- Poblacion.
- Provincia.
- Pais.

### Si el cliente es Administracion Publica

- Marcar `Es Administracion Publica`.
- Oficina contable DIR3.
- Organo gestor DIR3.
- Unidad tramitadora DIR3.
- Opcionalmente organo proponente.
- Referencia de expediente, contrato y pedido si existen.

## Campos nuevos

### Empresa

- `pais`

### Relacion empresa-tercero

- `facturae_es_administracion_publica`
- `facturae_dir3_oficina_contable`
- `facturae_dir3_organo_gestor`
- `facturae_dir3_unidad_tramitadora`
- `facturae_dir3_organo_proponente`
- `facturae_referencia_expediente`
- `facturae_referencia_contrato`
- `facturae_referencia_pedido`

### Factura emitida

- `facturae_xml_path`
- `facturae_generated_at`
- `facturae_status`
- `facturae_error`

## Flujo de uso

1. Abre la factura emitida.
2. Pulsa `Generar Facturae/FACe`.
3. Si faltan datos, la aplicacion muestra el listado de errores y no genera el XML.
4. Si todo es correcto, el usuario elige la ruta de salida.
5. Se crea un fichero con el formato `FACTURAE_<NIF_EMISOR>_<NUMERO_FACTURA>.xml`.

## Limitaciones actuales

- Esta primera fase genera XML Facturae sin firma electronica.
- No realiza envio automatico a FACe.
- La firma XAdES-EPES queda preparada como punto de extension: `sign_facturae_xml(xml_path, certificate_path, certificate_password)`.
- La arquitectura soporta factura rectificativa, pero el mapeo funcional avanzado de motivos puede requerir ajuste adicional segun casuistica real.

## Validacion en MiFacturae / FACe

- El XML puede revisarse con MiFacturae o con los validadores compatibles con Facturae 3.2.2.
- Para presentacion real en FACe normalmente sera necesario firmarlo con certificado digital.

## Pendiente para siguientes fases

- Firma XAdES-EPES.
- Presentacion automatica.
- Validacion contra XSD oficial en local si se incorpora el esquema al proyecto.
- Ajustes finos de codigos funcionales segun escenarios concretos de Administracion Publica.
