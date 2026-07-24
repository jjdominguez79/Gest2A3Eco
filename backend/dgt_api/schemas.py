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
    codigo_tasa: str | None = None
    modelo_620_presentado: bool | None = None
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


class DocumentoGeneradoCreate(BaseModel):
    tipo_documento: str
    titulo: str = ""
    fecha_generacion: str = ""
    ruta_docx: str | None = None
    ruta_pdf: str | None = None
    ruta_txt: str | None = None
    json_datos_generacion: dict[str, Any] = Field(default_factory=dict)
    hash_contenido: str | None = None
    estado: str = ""


class OrmModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)
