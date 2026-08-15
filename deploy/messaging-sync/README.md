# Paquete independiente de adjuntos de mensajeria

`deploy/messaging-sync` permite desplegar solo `messaging-sync` en Container
Manager, sin reconstruir ni sustituir `mail-sync`. Revisado el 2026-08-15.

El worker:

1. sincroniza el directorio de empresas desde PostgreSQL con el backend;
2. consulta adjuntos pendientes de la PWA;
3. reclama cada archivo con un identificador de worker;
4. descarga y verifica su SHA-256;
5. lo guarda en el repositorio documental compartido;
6. registra la ruta UNC en PostgreSQL y confirma la entrega al backend.

La confirmacion permite eliminar la copia temporal de Azure Blob. Si una
descarga falla, el elemento permanece recuperable para otro intento.

## Contenido y secretos

El paquete debe contener `compose.yaml`, `Dockerfile`, `requirements.txt`, el
directorio `sync_worker/` y:

```text
secrets/messaging_sync_token.txt
secrets/postgres_password.txt
```

`messaging_sync_token.txt` debe coincidir exclusivamente con
`MESSAGING_SYNC_TOKEN` del backend. No se reutilizan `DGT_INTERNAL_API_KEY` ni
un `WorkstationToken`.

## Configuracion

Revisar en `compose.yaml`:

- `MESSAGING_API_URL` y `MESSAGING_WORKER_ID`;
- `MESSAGING_SYNC_INTERVAL_SECONDS` (60 por defecto, minimo 30);
- `POSTGRES_HOST`, `POSTGRES_PORT`, `POSTGRES_DB` y `POSTGRES_USER`;
- el volumen Synology montado en `DOCUMENT_REPOSITORY_DIR`;
- `DOCUMENT_REPOSITORY_PUBLIC_DIR`, que debe ser la ruta UNC equivalente para
  los puestos Windows.

El usuario tecnico necesita:

```sql
GRANT SELECT, INSERT, UPDATE ON TABLE mensajeria_adjuntos_entrada TO gest2a3eco_sync;
GRANT SELECT ON TABLE empresas TO gest2a3eco_sync;
```

## Ejecucion y comprobacion

Desde la carpeta del paquete:

```text
docker compose config
docker compose up --build -d
docker compose ps
docker compose logs -f messaging-sync
```

El contenedor es de solo lectura salvo `/tmp` y el volumen documental. Las
peticiones GET/PUT reintentan errores transitorios hasta tres veces. Verificar
en PostgreSQL el estado de `mensajeria_adjuntos_entrada` y comprobar que la ruta
UNC registrada abre el mismo archivo guardado en el volumen.

La guia del despliegue conjunto con correo esta en
[`../mail-sync/README.md`](../mail-sync/README.md).
