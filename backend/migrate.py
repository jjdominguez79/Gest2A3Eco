#!/usr/bin/env python3
"""
Ejecutor de migraciones para Gest2A3Eco API.

Modos de uso
------------
Normal (aplica migraciones pendientes):
    python -m backend.migrate

Baseline para bases existentes sin schema_migrations (SOLO una vez):
    python -m backend.migrate --baseline-existing
    MIGRATE_BASELINE_EXISTING=true python -m backend.migrate

Verificacion read-only de una base existente:
    python -m backend.migrate --check-baseline

Garantias
---------
- schema_migrations: filename (PK) + SHA-256 + applied_at.
- Advisory lock PostgreSQL (key=4210201801) para serializar ejecuciones concurrentes.
- Toda la sesion usa UNA SOLA conexion (pool_size=1); sin deadlock.
- Base.metadata.create_all se llama UNICAMENTE en bases completamente vacias (cero tablas).
  En instalaciones nuevas: create_all crea el esquema ORM, 001 se registra sin ejecutar,
  002-038 se aplican normalmente.
- _run_startup_ddl y _create_initial_channels son reemplazados por 038_transition_legacy_startup.sql.
- Una segunda ejecucion sin migraciones pendientes no emite DDL ni escrituras.
  schema_migrations se crea sin IF NOT EXISTS; si ya existe no se emite CREATE TABLE.
- Checksums verificados: falla si un archivo ya aplicado ha cambiado.
- BASELINE_FILES es un frozenset cerrado; nunca se amplia automaticamente.
- --baseline-existing: registra exactamente BASELINE_FILES (39 entradas) y devuelve 0.
  No aplica migraciones pendientes (038+). Ejecutar de nuevo sin la flag para aplicarlas.
- Falla inmediatamente si schema_migrations esta vacia y dgt_expedientes existe (sin --baseline-existing).
- Falla inmediatamente si hay tablas de usuario pero falta dgt_expedientes (esquema parcial/desconocido).
"""
from __future__ import annotations

import argparse
import hashlib
import logging
import os
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import create_engine, text

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
logger = logging.getLogger("gest2a3eco.migrate")

MIGRATIONS_DIR = Path(__file__).resolve().parent / "migrations"
ADVISORY_LOCK_KEY = 4_210_201_801  # constante fija para este proyecto

CREATE_MIGRATIONS_TABLE = """
CREATE TABLE schema_migrations (
    filename   VARCHAR(255) PRIMARY KEY,
    checksum   CHAR(64)     NOT NULL,
    applied_at TIMESTAMPTZ  NOT NULL DEFAULT NOW()
)
"""

# Lista cerrada e inmutable de migraciones ya aplicadas en la base de produccion
# en el momento en que se introduce el sistema de control (2026-10-15).
# Evidencia: produccion tiene dgt_expedientes (001) y msg_staff_thread_mentions (037).
# UNA NUEVA MIGRACION NUNCA DEBE INCORPORARSE A ESTE CONJUNTO SIN REVISION MANUAL.
BASELINE_FILES: frozenset[str] = frozenset({
    "001_initial.sql",
    "002_flutter_messaging.sql",
    "003_ux_iteration.sql",
    "005_document_traceability.sql",
    "006_chat_inbox.sql",
    "007_internal_attachments_presence.sql",
    "008_client_platform_foundation.sql",
    "008_test_data_cleanup.sql",
    "009_client_documents.sql",
    "009_pre_release_global_cleanup.sql",
    "010_client_invoicing.sql",
    "011_messaging_notification_targets.sql",
    "012_feature_flag_audit.sql",
    "013_notification_log.sql",
    "014_notification_log_claim.sql",
    "015_client_customer_desktop_sync.sql",
    "016_profile_change_requests.sql",
    "017_organization_logo.sql",
    "018_client_certificate_requests.sql",
    "019_client_certificate_secrets.sql",
    "020_aapp_document_fiscal_year.sql",
    "021_dehu_notifications.sql",
    "022_dehu_automatic_sync.sql",
    "023_dehu_new_notifications.sql",
    "024_message_receipts.sql",
    "025_read_receipt_privacy.sql",
    "026_aeat_certificate_followup.sql",
    "026_message_edit_history.sql",
    "027_dehu_daily_sync_time.sql",
    "028_dev_notifications.sql",
    "029_dehu_activation_history.sql",
    "030_general_client_channel.sql",
    "031_invitation_content.sql",
    "032_group_avatars.sql",
    "033_profile_change_system_messages.sql",
    "034_subvenciones.sql",
    "035_subvenciones_boletines.sql",
    "036_subvenciones_finalidad_texto.sql",
    "037_staff_message_mentions.sql",
})

# ---------------------------------------------------------------------------
# Manifiesto de verificacion del baseline.
# Todos los elementos deben existir ANTES de registrar una sola fila.
# ---------------------------------------------------------------------------

# Tablas que deben existir en la base para aceptar el baseline.
BASELINE_REQUIRED_TABLES: frozenset[str] = frozenset({
    # Core expedientes (001)
    "dgt_expedientes", "dgt_partes", "dgt_vehiculos", "dgt_operaciones",
    "dgt_enlaces", "dgt_documentos", "dgt_solicitudes_subsanacion",
    "dgt_documentos_generados", "dgt_firmas", "dgt_eventos", "dgt_comunicaciones",
    # Mensajeria principal
    "msg_staff", "msg_organizations", "msg_clients", "msg_conversations",
    "msg_messages", "msg_attachments", "msg_events", "msg_staff_sessions",
    "msg_staff_threads", "msg_staff_thread_messages",
    # Menciones (037)
    "msg_staff_thread_mentions",
    # Documentos cliente (009)
    "client_documents",
    # Facturacion (010)
    "client_invoices", "client_invoice_series", "client_invoice_customers",
    "client_invoice_lines",
    # Certificados (018/019)
    "client_certificate_requests", "client_certificate_secrets",
    # DEHu (021-023)
    "client_dehu_notifications", "client_dehu_sync_batches",
    "client_dehu_mailbox_configs",
    # Notificaciones dev (028)
    "client_dev_mailbox_configs", "client_dev_notifications",
    # Subvenciones (034)
    "client_dehu_seen_references",
    "sub_convocatorias", "sub_preferencias", "sub_suscripciones", "sub_entregas",
    # Mensajeria auxiliar
    "msg_invitation_content", "msg_receipts", "msg_message_versions",
    # NOTA: schema_migrations NO se incluye aqui.
    # --check-baseline debe aprobar una base heredada antes de que esa tabla exista.
})

# Columnas esenciales: (tabla, columna).
# Evidencian que las migraciones posteriores a la inicial se aplicaron.
BASELINE_REQUIRED_COLUMNS: frozenset[tuple[str, str]] = frozenset({
    ("msg_staff_thread_mentions", "mentioned_staff_external_id"),  # 037 - nombre real
    ("msg_staff_thread_mentions", "internal_message_id"),          # 037 - nombre real
    ("sub_convocatorias", "resumen_estado"),                       # 036
    ("msg_invitation_content", "status"),                          # 031
    ("client_dehu_notifications", "holder_tax_id"),                # 021 - nombre real
    ("client_certificate_requests", "status"),                     # 018
    ("client_invoices", "fiscal_year"),                            # 020
    ("client_documents", "source_system"),                         # 009
    ("msg_receipts", "read_through_at"),                           # 024 - nombre real
})

# Indices que deben existir (evidencia de migraciones aplicadas).
BASELINE_REQUIRED_INDEXES: frozenset[str] = frozenset({
    # ix_msg_staff_thread_mentions_staff/message: presentes en 037 pero pueden
    # no estar en produccion si ese fichero fue baseline-registrado sin ejecutar.
    # Se crean idempotentemente en 038; no se exigen aqui.
    # ix_client_invoices_org / ix_client_documents_org: idem, de 010/009.
    # Solo se exigen indices que SABEMOS que existen en produccion desde antes de
    # cualquier baseline, es decir, los que estaban en el esquema heredado.
    "ix_sub_convocatorias_fecha",
    "ix_sub_convocatorias_visible",
    "ix_client_dehu_notification_org",
    "ix_client_cert_request_org",
    "ix_msg_invitation_content_status",
})


def _sha256(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def _sorted_migrations() -> list[Path]:
    """Devuelve los archivos .sql ordenados lexicograficamente por nombre."""
    return sorted(MIGRATIONS_DIR.glob("*.sql"), key=lambda p: p.name)


def _build_engine(url: str):
    """
    Construye un engine para el migrador con pool_size=1.

    Todo el trabajo bajo el advisory lock usa la misma conexion obtenida con
    'with eng.connect() as conn'. No se debe obtener ninguna conexion adicional.
    """
    if url.startswith("postgresql://"):
        url = f"postgresql+psycopg://{url.removeprefix('postgresql://')}"
    elif url.startswith("postgres://"):
        url = f"postgresql+psycopg://{url.removeprefix('postgres://')}"
    if not url.startswith("postgresql+psycopg://"):
        raise RuntimeError("migrate.py solo admite PostgreSQL.")
    return create_engine(url, pool_pre_ping=True, pool_size=1, max_overflow=0)


def _existing_tables(conn) -> set[str]:
    return set(conn.execute(text(
        "SELECT table_name FROM information_schema.tables "
        "WHERE table_schema = current_schema()"
    )).scalars())


def _existing_columns(conn, tables: frozenset[str]) -> set[tuple[str, str]]:
    tables_sql = ", ".join(f"'{t}'" for t in tables)
    return set(conn.execute(text(
        "SELECT table_name, column_name FROM information_schema.columns "
        f"WHERE table_schema = current_schema() AND table_name IN ({tables_sql})"
    )).tuples())


def _existing_indexes(conn, tables: frozenset[str]) -> set[str]:
    tables_sql = ", ".join(f"'{t}'" for t in tables)
    return set(conn.execute(text(
        "SELECT indexname FROM pg_indexes "
        f"WHERE schemaname = current_schema() AND tablename IN ({tables_sql})"
    )).scalars())


def _check_baseline_manifest(conn) -> list[str]:
    """
    Verifica el manifiesto del baseline. Devuelve lista de elementos ausentes.
    No modifica la base. Puede llamarse en modo read-only.
    """
    missing: list[str] = []

    # Tablas
    tables = _existing_tables(conn)
    for t in sorted(BASELINE_REQUIRED_TABLES):
        if t not in tables:
            missing.append(f"tabla: {t}")

    # Columnas (solo de tablas que existen para evitar ruido)
    col_tables = frozenset(t for (t, _) in BASELINE_REQUIRED_COLUMNS)
    existing_cols = _existing_columns(conn, col_tables)
    for (table, col) in sorted(BASELINE_REQUIRED_COLUMNS):
        if (table, col) not in existing_cols:
            missing.append(f"columna: {table}.{col}")

    # Indices
    idx_tables = frozenset({
        "msg_staff_thread_mentions", "sub_convocatorias", "client_invoices",
        "client_documents", "client_dehu_notifications", "client_certificate_requests",
        "msg_invitation_content",
    })
    existing_idx = _existing_indexes(conn, idx_tables)
    for idx in sorted(BASELINE_REQUIRED_INDEXES):
        if idx not in existing_idx:
            missing.append(f"indice: {idx}")

    return missing


def _verify_checksums(conn, applied: dict[str, str]) -> None:
    """
    Comprueba que los archivos ya registrados no han cambiado.
    Falla si un archivo registrado no existe en disco (no solo warning).
    """
    errores: list[str] = []
    for filename, registered_checksum in applied.items():
        migration_file = MIGRATIONS_DIR / filename
        if not migration_file.exists():
            errores.append(
                f"  {filename}: registrado en schema_migrations pero NO existe en disco. "
                "No elimines archivos de migracion ya aplicados."
            )
            continue
        current = _sha256(migration_file.read_text(encoding="utf-8"))
        if current != registered_checksum:
            errores.append(
                f"  {filename}: checksum registrado={registered_checksum[:12]}... "
                f"actual={current[:12]}..."
            )
    if errores:
        raise RuntimeError(
            "Problema con migraciones ya aplicadas:\n" + "\n".join(errores) + "\n"
            "No modifiques ni elimines archivos de migracion ya aplicados. "
            "Si el cambio es intencional, crea una nueva migracion."
        )


def _apply_baseline(conn) -> int:
    """
    Registra BASELINE_FILES como migraciones ya aplicadas SIN ejecutarlas.

    Requisitos previos (todos verificados antes de insertar cualquier fila):
    - El llamador paso --baseline-existing.
    - schema_migrations existe y esta vacia.
    - Todos los elementos del manifiesto BASELINE_REQUIRED_* existen.
    - Todos los archivos en BASELINE_FILES existen en disco.

    Devuelve el numero de archivos registrados.
    Lanza RuntimeError si cualquier verificacion falla (sin insertar nada).
    """
    # 1. Verificar manifiesto completo
    missing = _check_baseline_manifest(conn)
    if missing:
        raise RuntimeError(
            f"Baseline fallido: {len(missing)} elemento(s) ausentes en la base:\n"
            + "\n".join(f"  - {m}" for m in missing)
            + "\nVerifica que es la base correcta y que tiene el esquema esperado."
        )

    # 2. Verificar que todos los archivos del baseline existen en disco
    missing_files: list[str] = []
    for filename in sorted(BASELINE_FILES):
        path = MIGRATIONS_DIR / filename
        if not path.exists():
            missing_files.append(filename)
    if missing_files:
        raise RuntimeError(
            f"Baseline fallido: {len(missing_files)} archivo(s) de BASELINE_FILES "
            f"no existen en el repositorio:\n"
            + "\n".join(f"  - {f}" for f in missing_files)
            + "\nNo se puede registrar el baseline sin los archivos originales."
        )

    # 3. Registrar (todo o nada - si falla en mitad, el llamador hace rollback)
    registered = 0
    for migration_file in _sorted_migrations():
        if migration_file.name not in BASELINE_FILES:
            logger.info(
                "AVISO: %s no esta en BASELINE_FILES; quedara pendiente de aplicar",
                migration_file.name,
            )
            continue
        content = migration_file.read_text(encoding="utf-8")
        checksum = _sha256(content)
        conn.execute(
            text(
                "INSERT INTO schema_migrations (filename, checksum, applied_at) "
                "VALUES (:f, :c, NOW()) "
                "ON CONFLICT (filename) DO NOTHING"
            ),
            {"f": migration_file.name, "c": checksum},
        )
        registered += 1

    logger.info("Baseline: %d migraciones registradas como aplicadas (sin ejecutarse)", registered)
    return registered


def run_migrations(
    database_url: str | None = None,
    baseline_existing: bool = False,
    check_baseline: bool = False,
) -> int:
    """
    Aplica migraciones pendientes. Devuelve el numero de migraciones aplicadas.

    baseline_existing: registra BASELINE_FILES como ya aplicadas (sin ejecutar)
                       solo si schema_migrations esta vacia. Requiere flag explicito.
    check_baseline:    modo read-only; verifica el manifiesto sin modificar nada.
                       Devuelve 0 si OK, lanza RuntimeError si falta algo.
    """
    url = database_url or os.environ.get(
        "BACKEND_DATABASE_URL",
        os.environ.get("DGT_DATABASE_URL", ""),
    )
    if not url:
        raise RuntimeError(
            "BACKEND_DATABASE_URL es obligatorio para ejecutar migraciones."
        )

    eng = _build_engine(url)

    # ── Modo check-baseline (read-only) ──────────────────────────────────────
    if check_baseline:
        with eng.connect() as conn:
            missing = _check_baseline_manifest(conn)
        if missing:
            raise RuntimeError(
                f"check-baseline: {len(missing)} elemento(s) ausentes:\n"
                + "\n".join(f"  - {m}" for m in missing)
            )
        logger.info("check-baseline: OK, todos los elementos del manifiesto presentes")
        return 0

    applied_count = 0

    with eng.connect() as conn:
        conn.execute(text(f"SELECT pg_advisory_lock({ADVISORY_LOCK_KEY})"))
        logger.info("Advisory lock adquirido (key=%d)", ADVISORY_LOCK_KEY)

        original_exception: BaseException | None = None
        try:
            # Capturar tablas existentes ANTES de crear schema_migrations para
            # poder detectar esquemas parciales o desconocidos.
            pre_tables = _existing_tables(conn)
            user_tables_before = pre_tables - {"schema_migrations"}

            # Crear tabla de control SOLO si no existe.
            # Sin IF NOT EXISTS: la segunda ejecucion no emite ningun DDL.
            if "schema_migrations" not in pre_tables:
                conn.execute(text(CREATE_MIGRATIONS_TABLE))
                conn.commit()

            # Leer migraciones ya registradas: {filename: checksum}
            rows = conn.execute(
                text("SELECT filename, checksum FROM schema_migrations")
            ).all()
            applied: dict[str, str] = {r[0]: r[1] for r in rows}

            # Verificar checksums de migraciones ya aplicadas
            _verify_checksums(conn, applied)

            if not applied:
                if user_tables_before:
                    # Hay tablas de usuario. Determinar la situacion.
                    if "dgt_expedientes" not in user_tables_before:
                        raise RuntimeError(
                            "La base de datos contiene tablas de usuario "
                            f"({sorted(user_tables_before)[:5]}...) "
                            "pero le falta dgt_expedientes. "
                            "Este esquema es parcial o desconocido.\n"
                            "El migrador solo acepta:\n"
                            "  a) Bases completamente vacias (fresh install).\n"
                            "  b) Bases con el esquema completo de produccion "
                            "(dgt_expedientes + tablas hasta 037).\n"
                            "Si esta es una base de prueba parcial, eliminala y "
                            "comienza desde cero."
                        )
                    # dgt_expedientes existe: base de produccion sin control de versiones.
                    if not baseline_existing:
                        raise RuntimeError(
                            "La base de datos tiene el esquema de produccion "
                            "(dgt_expedientes existe) pero schema_migrations esta vacia.\n"
                            "Esta es probablemente la primera ejecucion del migrador "
                            "sobre una base existente.\n"
                            "Ejecuta primero:\n"
                            "    python -m backend.migrate --baseline-existing\n"
                            "Esto registrara las migraciones historicas sin ejecutarlas.\n"
                            "NO ejecutes sin --baseline-existing: intentaria aplicar 001_initial.sql "
                            "sobre una base existente y fallaria."
                        )
                    # Baseline solicitado explicitamente: registrar y TERMINAR.
                    # Las migraciones pendientes (038+) se aplican en la siguiente ejecucion normal.
                    logger.info("Modo baseline: registrando migraciones historicas sin ejecutar ...")
                    _apply_baseline(conn)
                    conn.commit()
                    logger.info(
                        "Baseline completado. Ejecuta de nuevo (sin --baseline-existing) "
                        "para aplicar las migraciones pendientes (038+)."
                    )
                    return 0
                else:
                    # Base completamente vacia (cero tablas de usuario antes de schema_migrations).
                    #
                    # Arquitectura de instalacion nueva:
                    # - Las tablas msg_*, client_*, sub_* son ORM-only: no las crea 001.
                    # - 002+ las modifican asumiendo que ya existen (ADD COLUMN, REFERENCES).
                    # - Secuencia correcta: create_all primero (crea TODO el esquema ORM),
                    #   luego registrar 001 sin ejecutar (sus tablas dgt_* ya existen via ORM),
                    #   luego aplicar 002-038 normalmente.
                    # - La segunda ejecucion no entra aqui porque applied no estara vacio.
                    logger.info(
                        "Base vacia detectada. "
                        "Ejecutando Base.metadata.create_all para instalar esquema ORM base."
                    )
                    from backend.api.database import Base
                    from backend.api import models             # noqa: F401  (dgt_*)
                    from backend.api import messaging_models  # noqa: F401  (msg_*)
                    from backend.api import client_models     # noqa: F401  (client_*)
                    from backend.api import subvenciones_models  # noqa: F401  (sub_*)
                    Base.metadata.create_all(bind=conn)
                    # Registrar 001_initial.sql como aplicado: sus tablas dgt_* fueron
                    # creadas por create_all. No lo ejecutamos para evitar "already exists".
                    migration_001 = MIGRATIONS_DIR / "001_initial.sql"
                    checksum_001 = _sha256(migration_001.read_text(encoding="utf-8"))
                    conn.execute(
                        text(
                            "INSERT INTO schema_migrations (filename, checksum, applied_at) "
                            "VALUES ('001_initial.sql', :c, NOW()) ON CONFLICT DO NOTHING"
                        ),
                        {"c": checksum_001},
                    )
                    applied["001_initial.sql"] = checksum_001
                    conn.commit()
                    logger.info(
                        "Esquema ORM creado; 001_initial.sql registrado sin ejecutar. "
                        "Se aplicaran las migraciones 002-038."
                    )

            # Aplicar migraciones pendientes
            for migration_file in _sorted_migrations():
                if migration_file.name in applied:
                    logger.debug("OK (ya aplicada): %s", migration_file.name)
                    continue

                content = migration_file.read_text(encoding="utf-8")
                checksum = _sha256(content)
                logger.info("Aplicando %s ...", migration_file.name)

                try:
                    conn.execute(text(content))
                    conn.execute(
                        text(
                            "INSERT INTO schema_migrations (filename, checksum, applied_at) "
                            "VALUES (:f, :c, NOW())"
                        ),
                        {"f": migration_file.name, "c": checksum},
                    )
                    conn.commit()
                    applied_count += 1
                    applied[migration_file.name] = checksum
                    logger.info("OK (nueva): %s", migration_file.name)
                except Exception:
                    conn.rollback()
                    logger.exception("FALLO en migracion %s", migration_file.name)
                    raise

            conn.commit()

        except BaseException as exc:
            original_exception = exc
            # Rollback antes de intentar liberar el lock.
            # Un InFailedSqlTransaction bloquearia pg_advisory_unlock si no hacemos rollback.
            try:
                conn.rollback()
            except Exception:
                pass  # Ya en estado de error; ignorar el error de rollback
            raise

        finally:
            # Liberar el advisory lock.
            # Si llegamos aqui con original_exception, la conexion ya fue revertida arriba.
            # Los advisory locks de sesion se liberan automaticamente al cerrar la conexion,
            # pero liberamos explicitamente para no retener el lock durante el cleanup de
            # SQLAlchemy del pool (que podria reutilizar la conexion).
            try:
                conn.execute(text(f"SELECT pg_advisory_unlock({ADVISORY_LOCK_KEY})"))
                if original_exception is None:
                    conn.commit()
            except Exception as unlock_exc:
                # No ocultar la excepcion original bajo un error de unlock.
                logger.warning(
                    "No se pudo liberar el advisory lock explicitamente "
                    "(se liberara al cerrar la conexion): %s",
                    unlock_exc,
                )

    logger.info("Migraciones completadas: %d nuevas aplicadas", applied_count)
    return applied_count


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Ejecutor de migraciones Gest2A3Eco"
    )
    parser.add_argument(
        "--baseline-existing",
        action="store_true",
        default=os.environ.get("MIGRATE_BASELINE_EXISTING", "").lower() in {
            "1", "true", "yes", "si"
        },
        help=(
            "En la primera ejecucion sobre una base existente sin schema_migrations, "
            "registra las migraciones historicas como aplicadas sin ejecutarlas. "
            "Solo para inicializacion. Tambien: MIGRATE_BASELINE_EXISTING=true."
        ),
    )
    parser.add_argument(
        "--check-baseline",
        action="store_true",
        default=False,
        help=(
            "Modo read-only: verifica que el manifiesto del baseline esta completo "
            "en la base actual. No crea schema_migrations ni modifica datos. "
            "Sale con codigo 0 si OK, 1 si falta algo."
        ),
    )
    args = parser.parse_args()

    try:
        count = run_migrations(
            baseline_existing=args.baseline_existing,
            check_baseline=args.check_baseline,
        )
        sys.exit(0)
    except Exception as exc:
        logger.exception("Error en migraciones: %s", exc)
        sys.exit(1)
