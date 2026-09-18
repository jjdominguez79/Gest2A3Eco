# Resguardos y seguimiento de certificados AEAT

Un PDF descargado no implica que la AEAT haya emitido el certificado. El
proveedor inspecciona el texto del PDF sin reescribir el documento firmado.
La pantalla "Obtener resguardo" puede contener un resguardo o el certificado.

## Ciclo de vida

- Certificado definitivo: `completed`, PDF final y resultado `POSITIVO` o
  `NEGATIVO` para al corriente/contratistas. No inferir el resultado del titulo.
- Resguardo con referencia verificable: `awaiting_issuance`, PDF en
  `receipt_document_id`, referencia en `external_reference`, fecha de primera
  presentacion en `submitted_at`, proxima consulta en `next_attempt_at`.
- Comprobaciones: 24, 48 y 72 horas; luego diarias con aviso de retraso. No
  interpretar el plazo como denegacion ni como fin del plazo legal.
- Formato desconocido, PDF escaneado, referencia ausente/ambigua o consulta no
  reconocida: `needs_action`. Conservar el documento y la marca de presentacion.
- Reintentar una solicitud ya presentada siempre consulta; nunca valida,
  firma ni presenta otra. No se permite eliminar/cancelar el expediente pendiente.
- Resguardo y certificado se archivan como documentos independientes. No
  reemplazar el primero al publicar el segundo.

## Limites y despliegue

Solo AEAT_CORRIENTE tiene configurada la URL oficial de recogida. Para los
otros tipos se archiva el documento pendiente y se requiere revision. La
automatizacion exige la referencia exacta en una fila o la ficha devuelta
por el codigo electronico exacto del resguardo (16 caracteres). Este codigo
no es la referencia numerica/TCT. El resguardo se lee por una API restringida
al expediente reclamado. Las descargas solo aceptan dominios AEAT permitidos.
El estado rotulado "Solicitado", sin certificado, conserva la espera.

Se ha reclasificado, con autorizacion, el resguardo existente de E00006:
el PDF original se conserva byte a byte y su consulta real confirma el estado
Solicitado. No se ha presentado una nueva solicitud oficial. Pruebas locales cubren el ciclo de cola,
identidad del expediente, archivo separado y ausencia de resultado inventado.

Desplegar conjuntamente backend (migracion 026, protocolo 3), worker
2026.09.18.8 (pypdf incluido) y Flutter. El protocolo evita que workers antiguos
reclamen expedientes pendientes y los presenten otra vez.

## Fuentes oficiales

- [Solicitud y recogida, incluidos resguardos](https://sede.agenciatributaria.gob.es/Sede/ayuda/consultas-informaticas/certificados-tributarios-ayuda-tecnica/certificado-encontrarse-corriente-obligaciones-tributarias.html)
- [Tramite G304 y estado de tramitacion](https://sede.agenciatributaria.gob.es/Sede/procedimientoini/G304.shtml)
- [Consulta de certificados expedidos y en tramitacion](https://sede.agenciatributaria.gob.es/Sede/procedimientoini/G331.shtml)
