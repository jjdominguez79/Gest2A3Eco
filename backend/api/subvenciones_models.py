"""Persistencia del area de ayudas y subvenciones."""

from __future__ import annotations

import uuid
from datetime import date, datetime, timezone

from sqlalchemy import (
    JSON,
    Boolean,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from backend.api.database import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def new_id() -> str:
    return str(uuid.uuid4())


class SubvencionConvocatoria(Base):
    __tablename__ = "sub_convocatorias"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    codigo_bdns: Mapped[str] = mapped_column(String(24), unique=True, index=True)
    titulo: Mapped[str] = mapped_column(Text)
    organo_nivel1: Mapped[str] = mapped_column(String(80), default="")
    organo_nivel2: Mapped[str] = mapped_column(String(250), default="")
    organo_nivel3: Mapped[str] = mapped_column(String(350), default="")
    ambito: Mapped[str] = mapped_column(String(16), index=True)
    alcance_nacional: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    ccaa_json: Mapped[list] = mapped_column(JSON, default=list)
    provincias_json: Mapped[list] = mapped_column(JSON, default=list)
    municipio_nombre: Mapped[str] = mapped_column(String(160), default="")
    municipio_slug: Mapped[str] = mapped_column(String(160), default="", index=True)
    es_provincial: Mapped[bool] = mapped_column(Boolean, default=False)
    fecha_recepcion: Mapped[date | None] = mapped_column(Date, index=True)
    fecha_inicio: Mapped[date | None] = mapped_column(Date)
    fecha_fin: Mapped[date | None] = mapped_column(Date, index=True)
    texto_inicio: Mapped[str] = mapped_column(Text, default="")
    texto_fin: Mapped[str] = mapped_column(Text, default="")
    abierto: Mapped[bool | None] = mapped_column(Boolean)
    presupuesto: Mapped[float | None] = mapped_column(Float)
    tipo_convocatoria: Mapped[str] = mapped_column(String(250), default="")
    finalidad: Mapped[str] = mapped_column(String(350), default="")
    beneficiarios_json: Mapped[list] = mapped_column(JSON, default=list)
    sectores_json: Mapped[list] = mapped_column(JSON, default=list)
    instrumentos_json: Mapped[list] = mapped_column(JSON, default=list)
    mrr: Mapped[bool] = mapped_column(Boolean, default=False)
    enlaces_json: Mapped[list] = mapped_column(JSON, default=list)
    resumen_json: Mapped[dict | None] = mapped_column(JSON)
    resumen_estado: Mapped[str] = mapped_column(String(20), default="pendiente", index=True)
    resumen_modelo: Mapped[str] = mapped_column(String(100), default="")
    hash_fuente: Mapped[str] = mapped_column(String(64), default="")
    hash_resumen: Mapped[str] = mapped_column(String(64), default="")
    raw_json: Mapped[dict] = mapped_column(JSON, default=dict)
    visible: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    revisada: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    creada_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    actualizada_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow,
    )


class SubvencionPreferencia(Base):
    __tablename__ = "sub_preferencias"

    client_id: Mapped[str] = mapped_column(
        ForeignKey("msg_clients.id", ondelete="CASCADE"), primary_key=True,
    )
    notificaciones_activas: Mapped[bool] = mapped_column(Boolean, default=False)
    incluir_nacionales: Mapped[bool] = mapped_column(Boolean, default=True)
    usar_territorio_empresa: Mapped[bool] = mapped_column(Boolean, default=True)
    creada_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    actualizada_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow,
    )


class SubvencionSuscripcion(Base):
    __tablename__ = "sub_suscripciones"
    __table_args__ = (
        UniqueConstraint("client_id", "nivel", "codigo", name="uq_sub_suscripcion"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    client_id: Mapped[str] = mapped_column(
        ForeignKey("msg_clients.id", ondelete="CASCADE"), index=True,
    )
    nivel: Mapped[str] = mapped_column(String(16), index=True)
    codigo: Mapped[str] = mapped_column(String(160), index=True)
    nombre: Mapped[str] = mapped_column(String(200))
    creada_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class SubvencionEjecucion(Base):
    __tablename__ = "sub_ejecuciones"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    inicio: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    fin: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    estado: Mapped[str] = mapped_column(String(20), default="en_curso", index=True)
    leidas: Mapped[int] = mapped_column(Integer, default=0)
    nuevas: Mapped[int] = mapped_column(Integer, default=0)
    actualizadas: Mapped[int] = mapped_column(Integer, default=0)
    resumidas: Mapped[int] = mapped_column(Integer, default=0)
    avisos_enviados: Mapped[int] = mapped_column(Integer, default=0)
    detalle: Mapped[str] = mapped_column(Text, default="")


class SubvencionConfiguracion(Base):
    __tablename__ = "sub_configuracion"

    id: Mapped[str] = mapped_column(String(20), primary_key=True, default="global")
    servicio_activo: Mapped[bool] = mapped_column(Boolean, default=True)
    avisos_activos: Mapped[bool] = mapped_column(Boolean, default=False)
    resumenes_ia_activos: Mapped[bool] = mapped_column(Boolean, default=False)
    updated_by: Mapped[str] = mapped_column(String(160), default="")
    actualizada_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow,
    )


class SubvencionEntrega(Base):
    __tablename__ = "sub_entregas"
    __table_args__ = (
        UniqueConstraint("client_id", "convocatoria_id", name="uq_sub_entrega"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    client_id: Mapped[str] = mapped_column(
        ForeignKey("msg_clients.id", ondelete="CASCADE"), index=True,
    )
    convocatoria_id: Mapped[str] = mapped_column(
        ForeignKey("sub_convocatorias.id", ondelete="CASCADE"), index=True,
    )
    estado: Mapped[str] = mapped_column(String(20), default="pendiente", index=True)
    intentos: Mapped[int] = mapped_column(Integer, default=0)
    dispositivos_enviados: Mapped[int] = mapped_column(Integer, default=0)
    ultimo_error: Mapped[str] = mapped_column(Text, default="")
    enviada_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    creada_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    actualizada_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow,
    )
