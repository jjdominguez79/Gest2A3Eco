# API Tramites DGT

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

La documentacion OpenAPI queda disponible en `/docs` y `/openapi.json`.
