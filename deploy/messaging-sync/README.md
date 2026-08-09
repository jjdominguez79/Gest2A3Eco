# Sincronizador de adjuntos de mensajeria para Synology

Paquete independiente para Container Manager. Descarga los adjuntos enviados
por clientes desde la PWA, comprueba su SHA-256, los guarda en el repositorio
documental compartido y registra la entrada pendiente de clasificar en
PostgreSQL.

Antes de crear el proyecto deben existir, sin saltos adicionales:

```text
secrets/messaging_sync_token.txt
secrets/postgres_password.txt
```

La imagen se construye separadamente del sincronizador de correo para no
detener ni reemplazar `gest2a3eco-mail-sync`.
