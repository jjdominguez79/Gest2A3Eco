# Sincronizador de adjuntos de mensajeria para Synology

Paquete independiente para Container Manager. Descarga los adjuntos enviados
por clientes desde Gestinem, comprueba su SHA-256, los guarda en el repositorio
documental compartido y registra la entrada pendiente de clasificar en
PostgreSQL. Tambien sincroniza el directorio de empresas para que el
administrador pueda elegir un cliente de Gest2A3Eco al crear una invitacion.
Los archivos se escriben dentro del volumen Docker, pero en PostgreSQL se
registra la ruta UNC indicada por `DOCUMENT_REPOSITORY_PUBLIC_DIR`, accesible
desde los puestos Windows.

Antes de crear el proyecto deben existir, sin saltos adicionales:

```text
secrets/messaging_sync_token.txt
secrets/postgres_password.txt
```

La imagen se construye separadamente del sincronizador de correo para no
detener ni reemplazar `gest2a3eco-mail-sync`.

El usuario PostgreSQL tecnico necesita permisos de escritura sobre la cola
local y de lectura sobre el directorio de empresas:

```sql
GRANT SELECT, INSERT, UPDATE ON TABLE mensajeria_adjuntos_entrada TO gest2a3eco_sync;
GRANT SELECT ON TABLE empresas TO gest2a3eco_sync;
```

Desde la carpeta que contiene `compose.yaml`, `Dockerfile`,
`requirements.txt`, `sync_worker` y `secrets`:

```text
docker compose up --build -d
docker compose logs -f messaging-sync
```

La periodicidad se configura con `MESSAGING_SYNC_INTERVAL_SECONDS` en
`compose.yaml`. El valor minimo admitido es 30 segundos y el valor inicial es
60 segundos. Cada ciclo deja en el registro el numero de clientes
sincronizados, los adjuntos pendientes y el tiempo hasta la siguiente consulta.
El `compose.yaml` no fuerza un controlador de logs: Container Manager utiliza
el controlador `db` predeterminado de Synology y muestra la salida en
**Contenedor > gest2a3eco-messaging-sync > Registro**.
