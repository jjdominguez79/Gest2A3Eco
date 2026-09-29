# gest2a3eco-mail-sync

Worker de Microsoft Graph para los buzones compartidos `oficina@gestinem.es` y
`documentacion@gestinem.es`. Escribe mensajes nuevos en PostgreSQL y mantiene
un cursor delta independiente por buzon. La etiqueta del origen se conserva
para la bandeja documental. Los secretos deben permanecer en `secrets/` y no
forman parte del paquete generado.

```sh
docker compose config
docker compose up --build -d
docker compose logs --tail=100 mail-sync
```
