# Circuito de documentos y facturas recibidas

**Ultima revision contra el codigo:** 2026-09-29.

## Fuente de verdad

`documentos_archivo` es el registro funcional unico de cada documento. Contiene
la empresa, el ejercicio, la categoria, el archivo definitivo, su hash, el canal
de origen y el estado contable visible para el usuario.

`documentos_ocr`, `facturas_recibidas_ocr`, `facturas_recibidas_docs` y
`asientos_contables` son proyecciones de proceso. La relacion es explicita:

- `documentos_archivo.ocr_documento_id` apunta al documento OCR.
- `facturas_recibidas_docs.documento_archivo_id` apunta al archivo definitivo.
- El identificador OCR se mantiene como `facturas_recibidas_docs.id` por
  compatibilidad con los datos existentes.

La inicializacion de PostgreSQL ejecuta un backfill idempotente. Si OCR ya tiene
un numero de asiento, lo copia al archivo y marca la factura como contabilizada.
Si solo existe un `suenlace.dat` generado, la marca como exportada a A3.

## Estados canonicos

1. `pendiente`: archivada, aun sin validacion contable.
2. `pendiente_contabilizar`: OCR revisado y listo para exportar.
3. `exportada_a3`: incluida en `suenlace.dat`, pendiente de que A3 asigne asiento.
4. `contabilizada`: el numero de asiento se ha confirmado en A3.
5. `contabilizada_manual`: contabilizacion en papel registrada por una persona.

Generar `suenlace.dat` nunca equivale a contabilizar. La transicion a
`contabilizada` exige un numero de asiento no vacio.

## Entradas

- Los buzones compartidos `oficina@gestinem.es` y
  `documentacion@gestinem.es` se sincronizan de forma independiente y conservan
  el buzón en `buzon_origen`.
- Los adjuntos de mensajeria, los correos clasificados y las cargas manuales
  terminan en `documentos_archivo` y usan la misma deduplicacion por empresa y
  SHA-256.
- La navegacion “Documentos recibidos” y el boton “Entradas pendientes” muestran
  correo y mensajeria en una unica bandeja. La tabla tecnica de mensajeria es
  solo una cola de entrada, no un archivo documental paralelo.
- Al clasificar una factura, se crea un trabajo OCR durable automáticamente. Si
  la cola no esta disponible, el documento permanece archivado y puede
  reintentarse desde Gestion documental.

## Sincronizacion del asiento

La captura desde Contabilidad u OCR actualiza en una sola
transaccion:

- `facturas_recibidas_docs.numero_asiento` y su estado;
- `asientos_contables.numero_asiento` y su estado;
- `documentos_ocr.estado`;
- `documentos_archivo.numero_asiento`, estado y metodo de contabilizacion.

Por ello todas las pantallas muestran el mismo resultado al refrescar.

La impresion de facturas recibidas esta disponible en Gestion documental desde
el momento del archivo y tambien en Contabilidad despues de validar el OCR.
Siempre utiliza el PDF definitivo y registra el numero de impresiones. Control
global de facturas es solo una vista de seguimiento y no modifica las facturas.

El circuito manual no exige validar el OCR. Desde Gestion documental se puede
indicar numero de factura, fecha de busqueda y concepto para localizarla en A3.
"Comprobar asiento en A3" la cierra como contabilizada manual cuando encuentra
su numero de asiento. Si el OCR termina mas tarde, respeta esa contabilizacion.
