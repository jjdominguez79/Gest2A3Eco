# Servicios de sincronizacion en Synology

El proyecto `deploy/mail-sync/compose.synology.yaml` ejecuta tres servicios sin
interfaz. Revisado contra los Compose y `sync_worker/` el 2026-08-15.

```text
Microsoft Graph / oficina@gestinem.es
  -> mail-sync
  -> PostgreSQL principal

Backend de mensajeria / Azure Blob temporal
  -> messaging-sync
  -> repositorio documental compartido + PostgreSQL principal

PostgreSQL principal
  -> master-data-sync
  -> Backend Railway (empresas, clientes y serie APP)
```

Los tres contenedores son `read_only`, eliminan capabilities Linux, aplican
`no-new-privileges` y usan `/tmp` mediante `tmpfs`.

## mail-sync

Consulta Microsoft Graph con credenciales de aplicacion y certificado. Escribe
los correos nuevos en `comunicaciones_sin_asignar` y mantiene el cursor delta y
el ultimo estado en `comunicaciones_sync`.

No descarga adjuntos automaticamente: guarda los metadatos e identificadores de
Graph en el payload. La aplicacion de escritorio lista y archiva solo los que el
usuario selecciona.

Variables:

- `GRAPH_TENANT_ID`, `GRAPH_CLIENT_ID`, `GRAPH_MAILBOX`.
- `GRAPH_CERTIFICATE_FILE`, `GRAPH_CERTIFICATE_PASSWORD_FILE`.
- `POSTGRES_HOST`, `POSTGRES_PORT`, `POSTGRES_DB`, `POSTGRES_USER` y
  `POSTGRES_PASSWORD_FILE`.
- `SYNC_INTERVAL_SECONDS`: minimo 30; 300 segundos por defecto.
- `IMPORT_EXISTING_ON_FIRST_RUN`: `false` establece un punto de partida sin
  importar el historico; `true` realiza una carga inicial deliberada.

## messaging-sync

Consulta la cola de adjuntos del backend, reclama cada archivo, verifica su
SHA-256, lo guarda en el volumen documental y confirma la entrega. La
sincronizacion del directorio empresarial pertenece exclusivamente a
`master-data-sync`.

Variables:

- `MESSAGING_API_URL`, `MESSAGING_SYNC_TOKEN_FILE` y `MESSAGING_WORKER_ID`.
- `MESSAGING_SYNC_INTERVAL_SECONDS`: minimo 30; 60 segundos por defecto.
- `DOCUMENT_REPOSITORY_DIR`: ruta del volumen dentro del contenedor.
- `DOCUMENT_REPOSITORY_PUBLIC_DIR`: ruta UNC que se registra para los puestos
  Windows.
- las mismas variables PostgreSQL separadas que usa `mail-sync`.

Las peticiones GET/PUT reintentan hasta tres veces errores de conexion, lectura,
`429` y errores transitorios `5xx`. Cada fichero conserva su estado en la cola,
por lo que un fallo no confirma ni elimina el contenido remoto.

## master-data-sync

Replica en una unica direccion los datos maestros del PostgreSQL de
Gest2A3Eco hacia el backend: ficha empresarial, clientes con subcuenta 430 y
configuracion de la serie online. No aplica cambios de Flutter en el maestro.

Variables:

- `CLIENT_MASTER_SYNC_API_URL`: URL publica de Railway.
- `CLIENT_MASTER_SYNC_TOKEN_FILE`: fichero con la misma clave aleatoria que la
  variable Railway `CLIENT_MASTER_SYNC_API_KEY`.
- `CLIENT_MASTER_SYNC_INTERVAL_SECONDS`: 300 segundos por defecto.
- `CLIENT_ONLINE_SERIES_CODE`: `APP` por defecto.
- las variables PostgreSQL de solo lectura compartidas con los otros workers.

## Secretos y volumen

Crear en `deploy/mail-sync/secrets/`, sin saltos adicionales:

```text
Gest2A3Eco-Sync.pfx
pfx_password.txt
postgres_password.txt
messaging_sync_token.txt
client_master_sync_token.txt
```

Los secretos estan excluidos de Git y se montan como solo lectura bajo
`/run/secrets`. `MESSAGING_SYNC_TOKEN` y `CLIENT_MASTER_SYNC_API_KEY` son
credenciales distintas y exclusivas de sus respectivos workers; no deben
reutilizarse como clave interna ni como token de un puesto.

El volumen documental predeterminado es
`/volume1/Doc_Compartidos/Gest2A3Eco`. Puede cambiarse mediante un `.env` junto
al Compose:

```text
DOCUMENT_REPOSITORY_HOST_PATH=/ruta/real/en/synology
```

La ruta UNC de `DOCUMENT_REPOSITORY_PUBLIC_DIR` debe apuntar a ese mismo
contenido desde Windows.

## Permisos PostgreSQL

El usuario tecnico necesita los permisos minimos que requieran ambos flujos:

```sql
GRANT SELECT, INSERT, UPDATE ON TABLE comunicaciones_sin_asignar TO gest2a3eco_sync;
GRANT SELECT, INSERT, UPDATE ON TABLE comunicaciones_sync TO gest2a3eco_sync;
GRANT SELECT, INSERT, UPDATE ON TABLE mensajeria_adjuntos_entrada TO gest2a3eco_sync;
GRANT SELECT ON TABLE empresas TO gest2a3eco_sync;
GRANT SELECT ON TABLE terceros TO gest2a3eco_sync;
GRANT SELECT ON TABLE terceros_empresas TO gest2a3eco_sync;
```

Los permisos exactos deben ajustarse a las operaciones del esquema desplegado;
no se debe conceder propiedad de la base al usuario del worker.

## Orden de instalacion en Synology

1. Desplegar primero el backend en Railway. Debe haber aplicado la migracion
   `015_client_customer_desktop_sync.sql` y tener una variable secreta nueva
   `CLIENT_MASTER_SYNC_API_KEY` con al menos 32 bytes aleatorios.
2. Copiar exactamente ese secreto, sin comillas ni salto final, a
   `deploy/mail-sync/secrets/client_master_sync_token.txt` en el Synology.
3. Actualizar el proyecto de Container Manager con todo el repositorio (el
   contexto de construccion del Compose apunta dos niveles por encima).
4. Conceder al usuario `gest2a3eco_sync` los `SELECT` indicados y comprobar que
   el Synology alcanza PostgreSQL en `192.168.0.19:5432` y Railway por HTTPS.
5. Reconstruir `messaging-sync` para retirar su antigua sincronizacion de
   empresas y crear `master-data-sync`. `mail-sync` no necesita cambios de
   configuracion.

El alta de clientes procedentes de Flutter y la importacion de sus facturas no
se ejecutan en Synology. Esa parte utiliza `invoice_worker`, que requiere
Windows y Microsoft Word para generar el PDF con la plantilla oficial. Debe
permanecer instalada como tarea programada en la maquina Windows destinada a
facturacion.

## Puesta en marcha y comprobacion

Desde la raiz del repositorio:

```text
docker compose -f deploy/mail-sync/compose.synology.yaml config
docker compose -f deploy/mail-sync/compose.synology.yaml build messaging-sync master-data-sync
docker compose -f deploy/mail-sync/compose.synology.yaml up -d messaging-sync master-data-sync
docker compose -f deploy/mail-sync/compose.synology.yaml ps
docker compose -f deploy/mail-sync/compose.synology.yaml logs -f mail-sync
docker compose -f deploy/mail-sync/compose.synology.yaml logs -f messaging-sync
docker compose -f deploy/mail-sync/compose.synology.yaml logs -f master-data-sync
```

Comprobar despues:

- `comunicaciones_sync` tiene una fila reciente para el buzon y sin error.
- los mensajes nuevos aparecen en `comunicaciones_sin_asignar`;
- `mensajeria_adjuntos_entrada` avanza de pendiente a archivado;
- el archivo descargado existe tanto en el volumen Linux como en la ruta UNC.
- `master-data-sync` informa del numero de empresas y clientes sincronizados.

Container Manager usa su controlador de logs predeterminado cuando el Compose
no fuerza otro, por lo que la salida tambien aparece en la pestana **Registro**.
