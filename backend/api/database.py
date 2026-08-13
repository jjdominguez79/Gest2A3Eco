from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from backend.api.config import get_settings


class Base(DeclarativeBase):
    pass


def build_engine(database_url: str | None = None):
    url = database_url or get_settings().database_url
    if url.startswith("postgresql://"):
        url = f"postgresql+psycopg://{url.removeprefix('postgresql://')}"
    elif url.startswith("postgres://"):
        url = f"postgresql+psycopg://{url.removeprefix('postgres://')}"
    if not url.startswith("postgresql+psycopg://"):
        raise RuntimeError("La API DGT solo admite PostgreSQL.")
    return create_engine(url, pool_pre_ping=True)


engine = build_engine()
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
