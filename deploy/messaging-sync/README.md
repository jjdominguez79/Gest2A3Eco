# Worker de adjuntos de mensajeria

Este directorio conserva el despliegue de desarrollo de `messaging-sync`. El
worker procesa exclusivamente adjuntos enviados desde Flutter; la
sincronizacion de empresas y clientes pertenece a `master-data-sync`.

La tabla `mensajeria_adjuntos_entrada` es una cola tecnica. El escritorio la
muestra junto con los correos pendientes y, al clasificar, mueve el archivo al
repositorio definitivo `documentos_archivo`; no existe un segundo archivo
documental exclusivo para mensajeria.

El paquete oficial para Synology, con la conexion real a PostgreSQL y las
instrucciones de actualizacion, se genera desde
[`../synology/`](../synology/README.md).
