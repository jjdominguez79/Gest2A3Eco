# Worker de correo

Este directorio conserva el despliegue de desarrollo del worker de Microsoft
Graph. En Synology, el proyecto oficial se llama
`gest2a3eco-mail-sync` y debe instalarse como proyecto independiente.

La estructura, el generador de paquetes y la migracion desde la antigua carpeta
`gest2a3eco-sync` estan documentados en
[`../synology/README.md`](../synology/README.md).

No se debe volver a crear un Compose conjunto para correo, mensajeria y datos
maestros: cada servicio tiene secretos, ciclo de actualizacion y carpeta
propios en Container Manager.
