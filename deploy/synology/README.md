# Despliegues independientes en Synology

Esta es la estructura oficial para el NAS `GestinemMain`. Cada worker es un
proyecto separado de Container Manager:

```text
/volume1/docker/
|-- gest2a3eco-mail-sync/
|-- gest2a3eco-messaging-sync/
|-- gest2a3eco-master-data-sync/
`-- gest2a3eco-postgres/
```

Los Compose usan la conexion real del NAS a PostgreSQL:

```text
POSTGRES_HOST=192.168.0.18
POSTGRES_PORT=5433
POSTGRES_DB=gest2a3eco
POSTGRES_USER=gest2a3eco_sync
```

El repositorio documental permanece en
`/volume1/Doc_Compartidos/Gest2A3Eco`, visible desde Windows como
`\\GestinemMain\Doc_Compartidos\Gest2A3Eco`.

## Generar los paquetes

Desde la raiz del repositorio, en PowerShell:

```powershell
.\deploy\synology\build_packages.ps1
```

Se generan tres carpetas autocontenidas bajo `dist_synology/`. El proceso no
copia secretos. Al actualizar un proyecto existente, copiar el contenido del
paquete sin eliminar ni reemplazar su carpeta `secrets/`.

## 1. Renombrar el proyecto de correo

El proyecto historico usa la carpeta `gest2a3eco-sync`, aunque el servicio y el
contenedor ya se llaman `gest2a3eco-mail-sync`. La migracion correcta es:

1. Detener el proyecto `gest2a3eco-sync` en Container Manager.
2. Renombrar `/volume1/docker/gest2a3eco-sync` a
   `/volume1/docker/gest2a3eco-mail-sync`.
3. Copiar sobre ella el paquete `dist_synology/gest2a3eco-mail-sync`,
   conservando estos secretos:

```text
secrets/Gest2A3Eco-Sync.pfx
secrets/pfx_password.txt
secrets/postgres_password.txt
```

4. Crear o importar el proyecto desde el nuevo `compose.yaml` y comprobar:

```sh
cd /volume1/docker/gest2a3eco-mail-sync
docker compose config
docker compose up --build -d
docker compose ps
docker compose logs --tail=100 mail-sync
```

## 2. Actualizar mensajeria

Copiar el paquete `dist_synology/gest2a3eco-messaging-sync` sobre
`/volume1/docker/gest2a3eco-messaging-sync`, conservando:

```text
secrets/messaging_sync_token.txt
secrets/postgres_password.txt
```

Despues:

```sh
cd /volume1/docker/gest2a3eco-messaging-sync
docker compose config
docker compose up --build -d
docker compose ps
docker compose logs --tail=100 messaging-sync
```

Esta version solo procesa adjuntos. La sincronizacion de empresas y clientes
pertenece exclusivamente al nuevo `master-data-sync`.

## 3. Crear master-data-sync

Copiar `dist_synology/gest2a3eco-master-data-sync` a
`/volume1/docker/gest2a3eco-master-data-sync` y crear:

```text
secrets/client_master_sync_token.txt
secrets/postgres_password.txt
```

`client_master_sync_token.txt` debe contener exactamente el valor de Railway
`CLIENT_MASTER_SYNC_API_KEY`, sin comillas. `postgres_password.txt` contiene la
clave del usuario tecnico `gest2a3eco_sync`.

```sh
cd /volume1/docker/gest2a3eco-master-data-sync
docker compose config
docker compose up --build -d
docker compose ps
docker compose logs --tail=100 master-data-sync
```

El flujo es unidireccional: PostgreSQL del escritorio hacia Railway. Flutter no
puede modificar los datos maestros de empresas ni asignar subcuentas.

## Permisos PostgreSQL

El usuario tecnico necesita, como minimo:

```sql
GRANT SELECT, INSERT, UPDATE ON TABLE comunicaciones_sin_asignar TO gest2a3eco_sync;
GRANT SELECT, INSERT, UPDATE ON TABLE comunicaciones_sync TO gest2a3eco_sync;
GRANT SELECT, INSERT, UPDATE ON TABLE mensajeria_adjuntos_entrada TO gest2a3eco_sync;
GRANT SELECT ON TABLE empresas TO gest2a3eco_sync;
GRANT SELECT ON TABLE terceros TO gest2a3eco_sync;
GRANT SELECT ON TABLE terceros_empresas TO gest2a3eco_sync;
```

El `invoice_worker` no se instala en Synology: requiere Windows y Microsoft
Word y debe continuar como tarea programada en el equipo de facturacion.
