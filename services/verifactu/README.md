# services/verifactu

Motor de trazabilidad fiscal Veri*FACTU para facturas emitidas desde Flutter.
Ver `docs/adr/0001-facturacion-autonoma-cliente.md`, seccion 9, para el
alcance declarado y las condiciones de activacion.

## Procedencia de las fuentes

Toda formula y estructura implementada aqui se ha contrastado, en esta
misma sesion de trabajo, contra dos documentos oficiales de la Agencia
Tributaria (Departamento de Informatica Tributaria, Subdireccion General de
Aplicaciones), descargados directamente de dominios `agenciatributaria.es` /
`agenciatributaria.gob.es`:

1. **"Sistemas Informaticos de Facturacion" (SIF/VERI\*FACTU), version 1.0.3**
   `https://sede.agenciatributaria.gob.es/static_files/AEAT_Desarrolladores/EEDD/IVA/VERI-FACTU/Veri-Factu_Descripcion_SWeb.pdf`
   — estructura de `RegistroAlta`/`RegistroAnulacion`, namespaces SOAP,
   ejemplos completos de XML de alta y anulacion (seccion 9.1.1.1 y
   equivalentes), formato de respuesta (`EstadoRegistro`,
   `CodigoErrorRegistro`, `DescripcionErrorRegistro`, `EstadoEnvío`, `CSV`).

2. **"Detalle de las especificaciones tecnicas para generacion de la huella o
   hash de los registros de facturacion", version 0.1.2 (27/08/2024)**
   `https://www.agenciatributaria.es/static_files/AEAT_Desarrolladores/EEDD/IVA/VERI-FACTU/Veri-Factu_especificaciones_huella_hash_registros.pdf`
   — algoritmo (SHA-256), campos de entrada y orden exacto, formato de
   concatenacion (`campo=valor&campo=valor`), formato de salida
   (hexadecimal mayusculas, 64 caracteres), y **tres ejemplos completos con
   resultado esperado**.

Los tres ejemplos del documento de huella se han verificado byte a byte en
esta sesion (`hashlib.sha256` sobre la cadena exacta del documento) y
coinciden exactamente con el resultado publicado por la AEAT. Se han fijado
como vectores de prueba de oro (golden tests) en
`tests/test_verifactu_hash.py`: si alguien cambia `hash.py` de forma que
deje de reproducir esos tres hashes exactos, los tests fallan.

## Lo que SI esta verificado con confianza alta

- El algoritmo y formato exacto de la huella/hash (SHA-256, mayusculas,
  concatenacion `campo=valor&...`, orden de campos para alta y para
  anulacion) — contrastado con 3 vectores oficiales exactos.
- Los nombres de los elementos XML y su jerarquia para `RegistroAlta` y
  `RegistroAnulacion`, el bloque `SistemaInformatico`, `Encadenamiento` /
  `RegistroAnterior`, y la cabecera `ObligadoEmision` — transcritos de
  ejemplos de XML reales incluidos en el documento 1.
- Que el primer registro de una cadena usa un campo `PrimerRegistro` en vez
  de `RegistroAnterior` (afirmado explicitamente en el documento 2, seccion
  5: *"en cuyo caso se debera indicar en el campo 'PrimerRegistro' (...) y
  no sera necesario informar los campos de los bloques 'RegistroAnterior'"*)
  — no se ha podido confirmar su posicion exacta en el arbol XML porque el
  diagrama correspondiente del documento 1 es una imagen que no se renderizo
  en la extraccion; se ha implementado como alternativa a
  `RegistroAnterior` dentro de `Encadenamiento`, que es la lectura mas
  directa del texto.
- Los valores de `EstadoRegistro` de la respuesta: `Correcto`,
  `AceptadoConErrores`, `Incorrecto` (documento 1, apartado 6.4.4 y 5.2).

## Lo que NO esta verificado (pendiente antes de activar el flag)

- El listado completo y oficial de codigos de `TipoFactura` (`F1`, `F2`,
  `R1`-`R5`, etc. — lista `L2` del anexo de la orden, no incluida en el
  documento 1 descargado) mas alla de `F1` (factura normal) y `R1`
  (rectificativa por sustitucion), unicos usados aqui.
- Validacion estructural contra el XSD oficial completo
  (`SuministroLR.xsd` / `SuministroInformacion.xsd`): no se ha descargado
  ni incorporado el XSD en esta sesion.
- El endpoint SOAP real y sus credenciales (certificado, entorno de
  pruebas vs produccion).
- Firma electronica de los registros (mencionada como documento aparte,
  "Especificaciones tecnicas para generacion de la firma electronica de los
  registros de facturacion", no descargado).

Mientras lo anterior siga pendiente, `VERIFACTU_SUBMISSION_ENABLED`
permanece en `false` y `NullAeatAdapter` es el unico adaptador activo: no
transmite nada. No se declara cumplimiento Veri\*FACTU en ningun documento
de este repositorio.

## Contenido

- `hash.py` — `compute_alta_hash`, `compute_anulacion_hash` (verificados,
  ver arriba).
- `models.py` — `AltaRegistroInput`, `AnulacionRegistroInput` (dataclasses).
- `builder.py` — construye el fragmento XML `RegistroAlta`/`RegistroAnulacion`
  (UTF-8, sin la envoltura SOAP completa: esa capa depende del adaptador de
  transporte real, todavia no implementado).
- `adapter.py` — `AeatSubmissionPort` (interfaz) y `NullAeatAdapter`
  (adaptador inerte usado mientras el envio real no este activo).

Este paquete es deliberadamente independiente de SQLAlchemy/FastAPI (como
`services/facturae/`, pensado para poder usarse tambien desde el escritorio
si hiciera falta). El bloqueo de fila sobre el estado de cadena por
organizacion (`ClientVerifactuChainState`, un obligado tributario = una
organizacion en este sistema) vive en
`backend/api/client_invoice_service.py::append_verifactu_alta`, junto al
resto de logica de emision que ya hace lo mismo para la numeracion de
series (`assign_invoice_number`).
