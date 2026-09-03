# gest2a3eco-mail-sync

Worker de Microsoft Graph para `oficina@gestinem.es`. Escribe mensajes nuevos
en PostgreSQL y mantiene el cursor delta. Los secretos deben permanecer en
`secrets/` y no forman parte del paquete generado.

```sh
docker compose config
docker compose up --build -d
docker compose logs --tail=100 mail-sync
```
