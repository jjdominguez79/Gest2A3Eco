# Sincronizador de comunicaciones en Synology

Servicio sin interfaz que consulta exclusivamente `oficina@gestinem.es` mediante
Microsoft Graph y registra los mensajes nuevos en PostgreSQL.

## Secretos requeridos

Crear en `deploy/mail-sync/secrets/` estos archivos, sin saltos adicionales:

- `Gest2A3Eco-Sync.pfx`: certificado privado exportado desde Windows.
- `pfx_password.txt`: contrasena del PFX.
- `postgres_password.txt`: contrasena del usuario `gest2a3eco_sync`.

Los secretos estan excluidos de Git. El contenedor los recibe como archivos de
solo lectura bajo `/run/secrets`.

## Ejecucion

Desde `deploy/mail-sync`:

```text
docker compose up --build -d
docker compose logs -f mail-sync
```

La periodicidad se configura con `SYNC_INTERVAL_SECONDS` en `compose.yaml`. El
valor minimo admitido es 30 segundos y el valor inicial es 300 (cinco minutos).

En la primera ejecucion, si la base de datos no contiene todavia un delta, se
establece el punto de partida sin importar mensajes antiguos. Para una carga
historica deliberada se puede cambiar `IMPORT_EXISTING_ON_FIRST_RUN` a `true`.
