# Esquemas Facturae 3.2.1

Copia local de los esquemas oficiales usados para validar de forma estricta
(offline) los ficheros Facturae que genera `services/facturae/`.

- `facturae_3_2_1.xsd`: esquema oficial de Facturae 3.2.1, descargado de
  `https://www.facturae.gob.es/content/dam/facturae/formato/versiones/Facturaev3_2_1.xml`
  (el gobierno lo sirve con extension `.xml` aunque es un XSD). Se ha quitado
  el BOM inicial y se ha redirigido el `xs:import` de xmldsig a la copia local
  `xmldsig-core-schema.xsd` para poder validar sin acceso a red. El contenido
  es identico byte a byte al original salvo esos dos cambios.
- `xmldsig-core-schema.xsd`: esquema `http://www.w3.org/TR/xmldsig-core/xmldsig-core-schema.xsd`,
  importado por el anterior (namespace `ds`, reservado para la futura firma
  XAdES-EPES). Copia local para validar sin red.

Descargados el 2026-08-21. `targetNamespace` verificado:
`http://www.facturae.es/Facturae/2014/v3.2.1/Facturae`, `elementFormDefault`
no declarado (por tanto `unqualified`: solo la raiz `<fe:Facturae>` va
cualificada con namespace, el resto de elementos van sin prefijo).

## Uso

`services/facturae/facturae_validator.py::validate_facturae_xml_content`
carga este esquema con `lxml` y valida cada XML generado antes de escribirlo
a disco. Si `lxml` no esta disponible o el esquema no se puede cargar, se
degrada a la comprobacion ligera de namespace/raiz que ya existia.

Ver tambien el skill `.agents/skills/facturae-xml/` (README.md versionado,
SKILL.md local), que documenta el proceso completo y usa
`tests/fixtures/facturae/A18.xml` (factura real aceptada por FACe) como
plantilla de referencia.
