# Worker de adjuntos de mensajeria

Este directorio conserva el despliegue de desarrollo de `messaging-sync`. El
worker procesa exclusivamente adjuntos enviados desde Flutter; la
sincronizacion de empresas y clientes pertenece a `master-data-sync`.

El paquete oficial para Synology, con la conexion real a PostgreSQL y las
instrucciones de actualizacion, se genera desde
[`../synology/`](../synology/README.md).
