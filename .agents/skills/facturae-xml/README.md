# facturae-xml

Genera y valida el XML Facturae para FACe en Gest2A3Eco contra el esquema
oficial, en vez de "a ojo".

## Que hace

Cuando se toca el generador de Facturae/FACe (`services/facturae/`), esta
skill obliga a validar cualquier duda de formato (namespace, prefijos, orden
de elementos, nombre de campos) contra dos fuentes de verdad concretas:

- **El XSD oficial de Facturae 3.2.1**, descargado de facturae.gob.es y
  guardado en `services/facturae/schemas/facturae_3_2_1.xsd`.
- **Una factura real aceptada por FACe**, guardada como golden file en
  `tests/fixtures/facturae/A18.xml`.

Fija en particular:

- Namespace y version correctos: `http://www.facturae.es/Facturae/2014/v3.2.1/Facturae`,
  `SchemaVersion 3.2.1` (no `2009/v3.2.2`, que era lo que habia antes).
- Que solo la raiz `<fe:Facturae>` lleva prefijo de namespace; el resto de
  elementos van sin cualificar (`elementFormDefault` no declarado = 
  `unqualified` en el XSD oficial). Verificado con `lxml.etree.XMLSchema`,
  no por comparacion visual.
- El orden exacto de `AdministrativeCentres` vs `LegalEntity`/`Individual`
  dentro de cada `Party`, de los campos de `Batch`, y el nombre correcto de
  `InvoiceIssueData` (no `IssueData`).
- Donde van realmente las referencias de expediente/contrato/pedido
  (`ReceiverContractReference`, `ReceiverTransactionReference`,
  `FileReference`): por linea, no a nivel de factura.

## Como se usa

`services/facturae/facturae_validator.py::validate_facturae_xml_content` ya
valida cada XML generado contra el XSD real (si `lxml` esta disponible,
degradando a una comprobacion ligera si no lo esta). Los tests de regresion
en `tests/test_facturae_golden_a18.py` comparan la salida del generador
contra el golden file en cada cambio.

```powershell
$env:PYTHONPATH = "."
python -m pytest tests/test_facturae_service.py tests/test_facturae_golden_a18.py -q
```

## Ver tambien

- [`SKILL.md`](./SKILL.md) — instrucciones completas para el agente (no se
  versiona en git, igual que el resto de `SKILL.md`/`CLAUDE.md` del repo).
- [`docs/facturae_face.md`](../../../docs/facturae_face.md) — flujo de
  usuario y campos obligatorios del formulario Facturae/FACe.
- [`services/facturae/schemas/README.md`](../../../services/facturae/schemas/README.md) — procedencia del XSD oficial.
