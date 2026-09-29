# Worker de correo

Este directorio conserva el despliegue de desarrollo del worker de Microsoft
Graph. En Synology, el proyecto oficial se llama
`gest2a3eco-mail-sync` y debe instalarse como proyecto independiente.

`GRAPH_MAIL_SOURCES` configura dos buzones compartidos independientes:
`oficina@gestinem.es` y `documentacion@gestinem.es`. Cada uno conserva su cursor
delta, etiqueta y trazabilidad de origen. `GRAPH_MAILBOX` solo se mantiene como
compatibilidad para configuraciones antiguas sin `GRAPH_MAIL_SOURCES`.

La estructura, el generador de paquetes y la migracion desde la antigua carpeta
`gest2a3eco-sync` estan documentados en
[`../synology/README.md`](../synology/README.md).

No se debe volver a crear un Compose conjunto para correo, mensajeria y datos
maestros: cada servicio tiene secretos, ciclo de actualizacion y carpeta
propios en Container Manager.
