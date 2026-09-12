# Gest2A3Eco AAPP worker

Worker aislado para procesar en Synology las solicitudes de certificados AEAT
y TGSS creadas desde el escritorio o Flutter.

Antes de arrancar, crear `secrets/aapp_worker_api_key.txt` con el mismo valor de
`AAPP_WORKER_API_KEY` configurado en Railway, sin comillas ni espacios.

```sh
docker compose config
docker compose -p gest2a3eco-aapp-worker-v2 up --build -d
docker compose ps
docker compose -p gest2a3eco-aapp-worker-v2 logs --tail=100 aapp-worker
```

Los certificados de cliente y sus contrasenas solo existen durante cada
tramite dentro del `tmpfs` del contenedor. Los diagnosticos se conservan en el
volumen `diagnostico/` y no deben contener el material criptografico.
