from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, JSON, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.api.database import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Expediente(Base):
    __tablename__ = "dgt_expedientes"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    referencia: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    tipo: Mapped[str] = mapped_column(String(64), default="compraventa_cambio_titularidad")
    titulo: Mapped[str] = mapped_column(String(200), default="")
    estado: Mapped[str] = mapped_column(String(40), default="borrador", index=True)
    responsable: Mapped[str] = mapped_column(String(120), default="")
    observaciones: Mapped[str] = mapped_column(Text, default="")
    version: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow, index=True)
    partes: Mapped[list["Parte"]] = relationship(back_populates="expediente", cascade="all, delete-orphan")
    vehiculo: Mapped["Vehiculo | None"] = relationship(back_populates="expediente", cascade="all, delete-orphan")
    operacion: Mapped["Operacion | None"] = relationship(back_populates="expediente", cascade="all, delete-orphan")


class Parte(Base):
    __tablename__ = "dgt_partes"
    __table_args__ = (UniqueConstraint("expediente_id", "rol"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    expediente_id: Mapped[str] = mapped_column(ForeignKey("dgt_expedientes.id", ondelete="CASCADE"), index=True)
    rol: Mapped[str] = mapped_column(String(16))
    estado: Mapped[str] = mapped_column(String(32), default="pendiente")
    tipo_persona: Mapped[str] = mapped_column(String(16), default="fisica")
    nombre: Mapped[str] = mapped_column(String(200), default="")
    nif: Mapped[str] = mapped_column(String(20), default="")
    email: Mapped[str] = mapped_column(String(254), default="")
    telefono: Mapped[str] = mapped_column(String(32), default="")
    datos: Mapped[dict] = mapped_column(JSON, default=dict)
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    expediente: Mapped[Expediente] = relationship(back_populates="partes")


class Vehiculo(Base):
    __tablename__ = "dgt_vehiculos"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    expediente_id: Mapped[str] = mapped_column(ForeignKey("dgt_expedientes.id", ondelete="CASCADE"), unique=True)
    matricula: Mapped[str] = mapped_column(String(20), default="")
    bastidor: Mapped[str] = mapped_column(String(40), default="")
    datos: Mapped[dict] = mapped_column(JSON, default=dict)
    expediente: Mapped[Expediente] = relationship(back_populates="vehiculo")


class Operacion(Base):
    __tablename__ = "dgt_operaciones"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    expediente_id: Mapped[str] = mapped_column(ForeignKey("dgt_expedientes.id", ondelete="CASCADE"), unique=True)
    datos: Mapped[dict] = mapped_column(JSON, default=dict)
    expediente: Mapped[Expediente] = relationship(back_populates="operacion")


class Enlace(Base):
    __tablename__ = "dgt_enlaces"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    expediente_id: Mapped[str] = mapped_column(ForeignKey("dgt_expedientes.id", ondelete="CASCADE"), index=True)
    rol: Mapped[str] = mapped_column(String(16))
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    last_access_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Documento(Base):
    __tablename__ = "dgt_documentos"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    expediente_id: Mapped[str] = mapped_column(ForeignKey("dgt_expedientes.id", ondelete="CASCADE"), index=True)
    rol: Mapped[str] = mapped_column(String(16))
    tipo: Mapped[str] = mapped_column(String(64))
    nombre_archivo: Mapped[str] = mapped_column(String(255))
    storage_key: Mapped[str] = mapped_column(String(500), unique=True)
    content_type: Mapped[str] = mapped_column(String(100))
    size: Mapped[int] = mapped_column(Integer)
    sha256: Mapped[str] = mapped_column(String(64))
    dataprius: Mapped[dict] = mapped_column("dataprius_json", JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class SolicitudSubsanacion(Base):
    __tablename__ = "dgt_solicitudes_subsanacion"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    expediente_id: Mapped[str] = mapped_column(ForeignKey("dgt_expedientes.id", ondelete="CASCADE"), index=True)
    rol: Mapped[str] = mapped_column(String(16))
    mensaje: Mapped[str] = mapped_column(Text)
    estado: Mapped[str] = mapped_column(String(32), default="pendiente")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class DocumentoGenerado(Base):
    __tablename__ = "dgt_documentos_generados"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    expediente_id: Mapped[str] = mapped_column(ForeignKey("dgt_expedientes.id", ondelete="CASCADE"), index=True)
    tipo: Mapped[str] = mapped_column(String(64))
    datos: Mapped[dict] = mapped_column(JSON, default=dict)


class Firma(Base):
    __tablename__ = "dgt_firmas"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    expediente_id: Mapped[str] = mapped_column(ForeignKey("dgt_expedientes.id", ondelete="CASCADE"), index=True)
    proveedor: Mapped[str] = mapped_column(String(64), default="")
    estado: Mapped[str] = mapped_column(String(32), default="pendiente")
    evidencia: Mapped[dict] = mapped_column(JSON, default=dict)


class Evento(Base):
    __tablename__ = "dgt_eventos"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    expediente_id: Mapped[str | None] = mapped_column(ForeignKey("dgt_expedientes.id", ondelete="SET NULL"), index=True)
    tipo: Mapped[str] = mapped_column(String(64), index=True)
    actor: Mapped[str] = mapped_column(String(120), default="")
    ip: Mapped[str] = mapped_column(String(64), default="")
    datos: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)


class Comunicacion(Base):
    __tablename__ = "dgt_comunicaciones"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    expediente_id: Mapped[str] = mapped_column(ForeignKey("dgt_expedientes.id", ondelete="CASCADE"), index=True)
    canal: Mapped[str] = mapped_column(String(32))
    destinatario: Mapped[str] = mapped_column(String(254))
    estado: Mapped[str] = mapped_column(String(32), default="preparada")
    datos: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Workstation(Base):
    """Puesto de escritorio registrado con token propio (hash SHA-256)."""
    __tablename__ = "workstations"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    name: Mapped[str] = mapped_column(String(120), unique=True)
    token_hash: Mapped[str] = mapped_column(String(64), index=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
