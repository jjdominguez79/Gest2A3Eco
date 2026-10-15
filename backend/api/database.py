from __future__ import annotations

import logging
import os
import re

from sqlalchemy import create_engine, event
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from backend.api.config import get_settings

logger = logging.getLogger("gest2a3eco.db.pool")


class Base(DeclarativeBase):
    pass


def _pool_int(name: str, default: int, min_val: int, max_val: int) -> int:
    raw = os.environ.get(name, str(default))
    try:
        val = int(raw)
    except (ValueError, TypeError):
        raise RuntimeError(f"{name} debe ser un entero, valor recibido: {raw!r}")
    if not (min_val <= val <= max_val):
        raise RuntimeError(
            f"{name}={val} fuera del rango permitido [{min_val}, {max_val}]"
        )
    return val


def _pg_timeout_ms(name: str, default: int) -> int:
    """Valida un timeout PostgreSQL en milisegundos. 0 significa desactivado."""
    raw = os.environ.get(name, str(default))
    try:
        val = int(raw)
    except (ValueError, TypeError):
        raise RuntimeError(f"{name} debe ser un entero en milisegundos, valor recibido: {raw!r}")
    if not (0 <= val <= 600_000):  # 0 = desactivado, max 10 minutos
        raise RuntimeError(
            f"{name}={val} fuera del rango permitido [0, 600000] ms"
        )
    return val


def _validate_app_name(name: str) -> str:
    """
    Valida application_name antes de incluirlo en 'options'.

    PostgreSQL limita NAMEDATALEN a 64 bytes (nombre <= 63 chars).
    Solo se permiten caracteres seguros para evitar inyeccion en el string options.
    """
    if not name:
        raise RuntimeError("DATABASE_APPLICATION_NAME no puede estar vacio")
    if len(name) > 63:
        raise RuntimeError(
            f"DATABASE_APPLICATION_NAME demasiado largo ({len(name)} chars, maximo 63)"
        )
    if not re.fullmatch(r"[A-Za-z0-9._-]+", name):
        raise RuntimeError(
            f"DATABASE_APPLICATION_NAME contiene caracteres no permitidos: {name!r}. "
            "Solo se admiten letras, digitos, guiones, puntos y subrayados."
        )
    return name


def build_engine(database_url: str | None = None):
    url = database_url or get_settings().database_url
    if url.startswith("postgresql://"):
        url = f"postgresql+psycopg://{url.removeprefix('postgresql://')}"
    elif url.startswith("postgres://"):
        url = f"postgresql+psycopg://{url.removeprefix('postgres://')}"
    if not url.startswith("postgresql+psycopg://"):
        raise RuntimeError("La API DGT solo admite PostgreSQL.")

    pool_size = _pool_int("DATABASE_POOL_SIZE", 5, 1, 50)
    max_overflow = _pool_int("DATABASE_MAX_OVERFLOW", 5, 0, 50)
    pool_timeout = _pool_int("DATABASE_POOL_TIMEOUT_SECONDS", 10, 1, 120)
    pool_recycle = _pool_int("DATABASE_POOL_RECYCLE_SECONDS", 300, 60, 3600)

    # Timeouts defensivos de PostgreSQL.
    # Se validan aqui para fallar en startup, no al obtener la primera conexion.
    # NOTA: se aplican a nivel de sesion mediante 'options' del driver (connect_args).
    # Con PgBouncer en modo transaccion no persisten entre transacciones; en ese
    # caso usa en su lugar:
    #   ALTER ROLE <usuario_api> SET idle_in_transaction_session_timeout = '30s';
    #   ALTER ROLE <usuario_api> SET statement_timeout = '30s';
    #   ALTER ROLE <usuario_api> SET lock_timeout = '5s';
    idle_in_tx_ms = _pg_timeout_ms("DATABASE_IDLE_IN_TX_TIMEOUT_MS", 30_000)
    stmt_timeout_ms = _pg_timeout_ms("DATABASE_STATEMENT_TIMEOUT_MS", 30_000)
    lock_timeout_ms = _pg_timeout_ms("DATABASE_LOCK_TIMEOUT_MS", 5_000)
    app_name = _validate_app_name(
        os.environ.get("DATABASE_APPLICATION_NAME", "gest2a3eco-api")
    )

    pg_options = (
        f"-c idle_in_transaction_session_timeout={idle_in_tx_ms}"
        f" -c statement_timeout={stmt_timeout_ms}"
        f" -c lock_timeout={lock_timeout_ms}"
        f" -c application_name={app_name}"
    )

    eng = create_engine(
        url,
        pool_pre_ping=True,
        pool_size=pool_size,
        max_overflow=max_overflow,
        pool_timeout=pool_timeout,
        pool_recycle=pool_recycle,
        connect_args={"options": pg_options},
    )

    @event.listens_for(eng, "checkout")
    def _on_checkout(dbapi_conn, conn_record, conn_proxy):  # noqa: ARG001
        pool = eng.pool
        overflow = pool.overflow()
        if overflow > 0:
            logger.warning(
                "pool.checkout overflow=%d checkedout=%d size=%d",
                overflow,
                pool.checkedout(),
                pool.size(),
            )

    @event.listens_for(eng, "invalidate")
    def _on_invalidate(dbapi_conn, conn_record, exception):  # noqa: ARG001
        exc_name = type(exception).__name__ if exception else "manual"
        logger.warning("pool.invalidate reason=%s", exc_name)

    return eng


engine = build_engine()
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def get_db():
    """Generador de sesion para FastAPI Depends. Hace rollback ante excepcion."""
    db: Session = SessionLocal()
    try:
        yield db
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
