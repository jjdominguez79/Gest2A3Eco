# gest2a3eco-messaging-sync

Worker de adjuntos del cliente Flutter. Descarga, verifica y archiva cada
fichero en el repositorio documental. No sincroniza empresas ni clientes.

```sh
docker compose config
docker compose up --build -d
docker compose logs --tail=100 messaging-sync
```
