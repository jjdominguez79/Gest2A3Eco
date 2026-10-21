# Plan de despliegue en dos etapas — Fase 1 estabilización PostgreSQL

Fecha de redacción: 2026-10-15
Advisory lock key: `4210201801`

---

## Etapa A — Correcciones de sesión, pool, SSE y health (sin DDL)

### Objetivo
Desplegar la corrección de la fuga de sesión SSE, el pool hardening y los
health endpoints **sin tocar el esquema**. El startup y el pre-deploy no
ejecutan DDL.

### Prerrequisitos
- `backend/api/app.py`: startup sin DDL (ya completado).
- `backend/api/messaging_api.py`: SSE sin `Depends(get_db)` (ya completado).
- `railway.toml`: sin `preDeployCommand` (no activar todavía).

### Verificación previa (read-only)
```bash
# Desde una máquina con acceso a la base de producción:
BACKEND_DATABASE_URL="postgresql://..." \
    python -m backend.migrate --check-baseline
# Debe terminar con: "check-baseline: OK" (o listar ausentes).
```

### Rollback Etapa A
```bash
# Railway: revertir al commit anterior
railway redeploy <commit-anterior>
# No hay cambios de esquema que revertir.
```

### Criterio de avance a Etapa B
- Al menos 24 horas sin conexiones `idle in transaction` en el pool.
- `/health/live` y `/health/ready` respondiendo correctamente.
- Logs de pool sin `pool.checkout overflow`.

---

## Etapa B — Baseline, migración de transición y activación del pre-deploy

### Objetivo
Registrar el historial de migraciones, aplicar `038_transition_legacy_startup.sql`
y activar `preDeployCommand`.

### Pasos

**B.1 — Copia de seguridad**
```bash
pg_dump $BACKEND_DATABASE_URL -Fc -f backup_pre_fase1_$(date +%Y%m%d_%H%M%S).dump
# Verificar restauración en entorno de prueba antes de continuar.
```

**B.2 — Baseline (una sola vez)**
```bash
BACKEND_DATABASE_URL="postgresql://..." \
    python -m backend.migrate --baseline-existing
# Registra los 39 archivos de BASELINE_FILES en schema_migrations sin ejecutarlos.
# Termina sin aplicar migraciones pendientes (devuelve 0).
# Verificar: SELECT COUNT(*) FROM schema_migrations; -- debe ser exactamente 39
# Verificar ausencia de 038 y 039:
#   SELECT filename FROM schema_migrations WHERE filename >= '038'; -- 0 filas
```

**B.3 — Migración de transición**
```bash
BACKEND_DATABASE_URL="postgresql://..." \
    python -m backend.migrate
# Aplica, en orden, 038_transition_legacy_startup.sql y
# 039_chat_inbox_preferences.sql.
# Logs esperados: ambas migraciones terminan con "OK (nueva)".
# Verificar: SELECT COUNT(*) FROM schema_migrations; -- debe ser exactamente 41
```

**B.4 — Verificar idempotencia (no DDL en segunda ejecución)**
```bash
BACKEND_DATABASE_URL="postgresql://..." \
    python -m backend.migrate
# Logs esperados: "Migraciones completadas: 0 nuevas aplicadas"
# No debe aparecer ningún ALTER TABLE ni CREATE INDEX.
```

**B.5 — Activar pre-deploy en railway.toml**
```toml
[deploy]
preDeployCommand = "python -m backend.migrate"
```

**B.6 — Cambiar healthcheck a /health/ready**
En el panel de Railway, cambiar el healthcheck a `/health/ready` solo cuando
se confirme que responde en < 1 s consistentemente.

### Rollback Etapa B

**Si falla B.2 (baseline)**:
```bash
# schema_migrations fue creada pero puede estar vacía o incompleta.
# Simplemente borrar y reintentar:
PGPASSWORD=... psql $BACKEND_DATABASE_URL -c "DROP TABLE IF EXISTS schema_migrations;"
# Corregir el problema e intentar de nuevo con --baseline-existing.
```

**Si falla B.3 (migraciones 038 o 039)**:
```bash
# La migración falló y fue revertida automáticamente (rollback por excepción).
# La transaccion fallida no queda registrada en schema_migrations.
# Para rollback completo de la etapa B:
PGPASSWORD=... psql $BACKEND_DATABASE_URL -c "DROP TABLE IF EXISTS schema_migrations;"
# Revertir railway.toml al estado sin preDeployCommand.
# No hay columnas nuevas que revertir (el rollback de la TX las deshizo).
```

**Si hay degradación tras B.5**:
```bash
# Revertir railway.toml eliminando preDeployCommand.
railway redeploy <commit-anterior-con-preDeployCommand-desactivado>
# El schema permanece en el ultimo estado migrado correctamente.
```

---

## Clave del advisory lock

`ADVISORY_LOCK_KEY = 4210201801`

Los advisory locks de sesión se liberan automáticamente al cerrar la conexión.
No intentar liberarlos desde otra conexión; si el proceso migrador es interrumpido,
el lock se libera al caducar la conexión de PostgreSQL.

Para verificar si hay un lock activo:
```sql
SELECT pid, granted, classid, objid
FROM pg_locks
WHERE locktype = 'advisory' AND objid = 4210201801;
```
