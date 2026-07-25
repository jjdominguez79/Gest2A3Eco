# API Tramites DGT

Backend independiente para expedientes DGT. En desarrollo usa SQLite; en
produccion acepta PostgreSQL mediante `DGT_DATABASE_URL`.

```powershell
pip install -r backend/requirements.txt
$env:DGT_INTERNAL_API_KEY = "cambiar-en-produccion"
uvicorn backend.dgt_api.app:app --reload
```

Variables:

- `DGT_DATABASE_URL`: URL SQLAlchemy (por defecto `sqlite:///./dgt_api.db`).
- `DGT_INTERNAL_API_KEY`: credencial de Gest2A3Eco (obligatoria fuera de tests).
- `DGT_PUBLIC_BASE_URL`: base de enlaces HTTPS.
- `DGT_TOKEN_TTL_HOURS`: caducidad, 168 horas por defecto.
- `DGT_STORAGE_DIR`: almacenamiento privado local de desarrollo.
- `REDSYS_ENVIRONMENT`: `test` durante esta fase.
- `REDSYS_MERCHANT_CODE`: codigo de comercio/FUC de pruebas.
- `REDSYS_TERMINAL`: terminal de pruebas.
- `REDSYS_SECRET_KEY`: clave de firma, solo en variables privadas.
- `REDSYS_NOTIFICATION_URL`: callback HTTPS publico para la confirmacion PayGold.
- `REDSYS_TIMEOUT`: timeout REST; se fuerza un minimo de 40 segundos.

PayGold se prepara en modo seguro: la aplicacion solicita un enlace a Redsys, pero
nunca recibe ni almacena datos de tarjeta. El endpoint de notificacion es
`POST /api/v1/pagos/redsys/notificacion`.

La documentacion OpenAPI queda disponible en `/docs` y `/openapi.json`.
