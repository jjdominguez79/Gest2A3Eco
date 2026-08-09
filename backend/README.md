# API Tramites DGT y Mensajeria

Backend independiente para expedientes DGT. Usa PostgreSQL exclusivamente
mediante `DGT_DATABASE_URL`.

```powershell
pip install -r backend/requirements.txt
$env:DGT_INTERNAL_API_KEY = "cambiar-en-produccion"
uvicorn backend.dgt_api.app:app --reload
```

Variables:

- `DGT_DATABASE_URL`: URL SQLAlchemy de PostgreSQL. Es obligatoria.
- `DGT_INTERNAL_API_KEY`: credencial de Gest2A3Eco (obligatoria fuera de tests).
- `DGT_PUBLIC_BASE_URL`: base de enlaces HTTPS.
- `DGT_TOKEN_TTL_HOURS`: caducidad, 168 horas por defecto.
- `DGT_STORAGE_DIR`: almacenamiento privado local de desarrollo.
- `MESSAGING_PUBLIC_BASE_URL`: origen HTTPS del portal `/mensajes`.
- `MESSAGING_AZURE_CONNECTION_STRING`: almacenamiento temporal de adjuntos de
  mensajeria. Debe configurarse en produccion; el disco local es solo para desarrollo.
- `MESSAGING_AZURE_CONTAINER`: contenedor privado, `mensajeria-temporal` por defecto.
- `MESSAGING_ATTACHMENT_DAYS`: disponibilidad de documentos enviados al cliente;
  nunca puede ser inferior a 15 y por defecto son 30 dias.
- `MESSAGING_GRAPH_*`: credenciales de aplicacion de Microsoft Graph
  (`TENANT_ID`, `CLIENT_ID`, `CLIENT_SECRET` y `FROM`) para enviar invitaciones,
  recuperaciones y avisos desde el backend. La aplicacion de Azure necesita el
  permiso de aplicacion `Mail.Send` con consentimiento de administrador.
- `MESSAGING_GRAPH_INVITATION_FROM`: buzon autorizado desde el que salen las
  invitaciones creadas por el administrador.
- `MESSAGING_STAFF_*`: configuracion del acceso Microsoft 365 de empleados. Si
  no se indican `TENANT_ID`, `CLIENT_ID` y `CLIENT_SECRET`, se reutilizan los de
  Graph. `ADMIN_EMAILS` define los administradores iniciales y
  `ALLOWED_DOMAIN` restringe el dominio corporativo.
- `MESSAGING_SYNC_TOKEN`: secreto exclusivo del recolector de adjuntos del
  Synology; no debe reutilizar la clave general de la API.
- `MESSAGING_VAPID_PUBLIC_KEY`, `MESSAGING_VAPID_PRIVATE_KEY` y
  `MESSAGING_VAPID_SUBJECT`: credenciales Web Push para avisar a los empleados
  aunque la PWA no este abierta.
- `MESSAGING_SMTP_*`: respaldo opcional cuando Graph no esta configurado. Los
  avisos de mensajes se envian solo si el cliente no mantiene una conexion
  activa con la PWA.

En cada puesto de Gest2A3Eco se configuran `messaging_api_url` y
`messaging_api_key` (pueden reutilizar inicialmente la URL y clave internas de
DGT). En el primer acceso se registra una credencial revocable propia del puesto
en `messaging_device_token`. Los adjuntos recibidos se descargan a la entrada del repositorio documental
compartido, se verifican por SHA-256 y se elimina entonces la copia temporal cloud.

La documentacion OpenAPI queda disponible en `/docs` y `/openapi.json`.
