from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class ExpedienteCreate(BaseModel):
    titulo: str = ""
    responsable: str = ""
    observaciones: str = ""
    vendedor_email: str = ""
    vendedor_telefono: str = ""
    comprador_email: str = ""
    comprador_telefono: str = ""


class ExpedientePatch(BaseModel):
    titulo: str | None = None
    estado: str | None = None
    responsable: str | None = None
    observaciones: str | None = None
    version: int | None = Field(default=None, ge=1)


class PartePatch(BaseModel):
    tipo_persona: str = "fisica"
    nombre: str = ""
    nif: str = ""
    email: str = ""
    telefono: str = ""
    datos: dict[str, Any] = Field(default_factory=dict)


class SubsanacionCreate(BaseModel):
    rol: str
    mensaje: str = Field(min_length=3)


class OrmModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)
