# gest2a3eco-master-data-sync

Worker unidireccional de datos maestros: PostgreSQL del escritorio hacia el
backend Railway. Sincroniza empresas, clientes contables y la serie `APP`.

```sh
docker compose config
docker compose up --build -d
docker compose logs --tail=100 master-data-sync
```
