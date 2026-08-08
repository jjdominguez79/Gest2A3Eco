# Sincronizador de comunicaciones en Synology

Servicio sin interfaz que consulta exclusivamente `oficina@gestinem.es` mediante
Microsoft Graph y registra los mensajes nuevos en PostgreSQL.

Este contenedor **no tiene base de datos propia**. Es un proceso sin estado
persistente: se puede reiniciar o recrear sin perdida de datos siempre que
mantenga acceso a PostgreSQL y a los secretos de Graph.

## Arquitectura

```text
Microsoft Graph / oficina@gestinem.es
  -> contenedor Synology gest2a3eco-mail-sync
  -> PostgreSQL principal de Gest2A3Eco
```

La base de destino se define en `compose.yaml` / `compose.synology.yaml` con:

- `POSTGRES_HOST`: host de la maquina virtual que sirve PostgreSQL.
- `POSTGRES_PORT`: puerto PostgreSQL.
- `POSTGRES_DB`: base principal de Gest2A3Eco.
- `POSTGRES_USER`: usuario tecnico del sincronizador, normalmente
  `gest2a3eco_sync`.
- `POSTGRES_PASSWORD_FILE`: secreto con la contrasena del usuario tecnico.

El sincronizador escribe en estas tablas de la base principal:

- `comunicaciones_sin_asignar`: mensajes nuevos pendientes de asignar a cliente
  o responsable.
- `comunicaciones_sync`: cursor `delta_link`, fecha de ultima sincronizacion y
  ultimo error.

No descarga adjuntos automaticamente. Solo guarda `tiene_adjuntos` y los
identificadores de Graph dentro del `payload_json`. La descarga/importacion de
adjuntos se hace desde la aplicacion de escritorio cuando el usuario lo decide.

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

## Comprobacion operativa

Para verificar que el contenedor esta funcionando:

```text
docker compose ps
docker compose logs -f mail-sync
```

En PostgreSQL, la tabla `comunicaciones_sync` debe mostrar una fila para
`oficina@gestinem.es` con `ultima_sincronizacion` reciente y `ultimo_error`
vacio. Los mensajes nuevos aparecen primero en `comunicaciones_sin_asignar`.
