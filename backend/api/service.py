from __future__ import annotations

import re
from datetime import timedelta

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from backend.api.config import get_settings
from backend.api.models import Enlace, Evento, Expediente, Operacion, Parte, Vehiculo
from backend.api.security import hash_token, new_token, utcnow

ROLES = {"vendedor", "comprador"}


def serializar_expediente(item: Expediente) -> dict:
    partes = {
        parte.rol: {
            "id": parte.id,
            "rol": parte.rol,
            "estado": parte.estado,
            "tipo_persona": parte.tipo_persona,
            "nombre": parte.nombre,
            "nif": parte.nif,
            "email": parte.email,
            "telefono": parte.telefono,
            "datos": parte.datos or {},
            "submitted_at": parte.submitted_at,
        }
        for parte in item.partes
    }
    vendedor_datos = next(
        (parte.datos or {} for parte in item.partes if parte.rol == "vendedor"),
        {},
    )
    vehiculo = dict(item.vehiculo.datos or {}) if item.vehiculo else {}
    vehiculo["matricula"] = (
        item.vehiculo.matricula if item.vehiculo and item.vehiculo.matricula
        else vendedor_datos.get("vehiculo_matricula", "")
    )
    vehiculo["bastidor"] = (
        item.vehiculo.bastidor if item.vehiculo and item.vehiculo.bastidor
        else vendedor_datos.get("vehiculo_bastidor", "")
    )
    operacion = dict(item.operacion.datos or {}) if item.operacion else {}
    for key in (
        "precio_venta", "fecha_operacion", "hora_entrega", "forma_pago", "llaves_vehiculo",
    ):
        if not operacion.get(key) and vendedor_datos.get(key) not in (None, ""):
            operacion[key] = vendedor_datos[key]
    return {
        "id": item.id,
        "referencia": item.referencia,
        "tipo": item.tipo,
        "titulo": item.titulo or f"Cambio de titularidad {vehiculo.get('matricula') or item.referencia}",
        "estado": item.estado,
        "responsable": item.responsable,
        "observaciones": item.observaciones,
        "version": item.version,
        "created_at": item.created_at,
        "updated_at": item.updated_at,
        "partes": partes,
        "vehiculo": vehiculo,
        "operacion": operacion,
    }


def cargar_expediente(db: Session, expediente_id: str) -> Expediente:
    stmt = (
        select(Expediente)
        .where(Expediente.id == expediente_id)
        .options(selectinload(Expediente.partes), selectinload(Expediente.vehiculo), selectinload(Expediente.operacion))
    )
    item = db.scalar(stmt)
    if not item:
        raise HTTPException(404, "Expediente no encontrado")
    return item


def siguiente_referencia(db: Session) -> str:
    year = utcnow().year
    prefix = f"DGT-{year}-"
    refs = db.scalars(select(Expediente.referencia).where(Expediente.referencia.like(f"{prefix}%"))).all()
    nums = [int(match.group(1)) for ref in refs if (match := re.fullmatch(rf"{re.escape(prefix)}(\d+)", ref))]
    return f"{prefix}{max(nums, default=0) + 1:04d}"


def crear_expediente(db: Session, payload) -> Expediente:
    referencia = siguiente_referencia(db)
    item = Expediente(
        referencia=referencia,
        titulo=payload.titulo.strip() or f"Cambio de titularidad {referencia}",
        responsable=payload.responsable,
        observaciones=payload.observaciones,
    )
    item.partes = [
        Parte(rol="vendedor", email=payload.vendedor_email, telefono=payload.vendedor_telefono),
        Parte(rol="comprador", email=payload.comprador_email, telefono=payload.comprador_telefono),
    ]
    item.vehiculo = Vehiculo(datos={})
    item.operacion = Operacion(datos={})
    db.add(item)
    db.flush()
    registrar_evento(db, item.id, "expediente_creado", "gest2a3eco")
    return item


def crear_enlace(db: Session, item: Expediente, rol: str) -> dict:
    if rol not in ROLES:
        raise HTTPException(422, "Rol no valido")
    now = utcnow()
    for active in db.scalars(
        select(Enlace).where(Enlace.expediente_id == item.id, Enlace.rol == rol, Enlace.revoked_at.is_(None))
    ):
        active.revoked_at = now
    token = new_token()
    expires_at = now + timedelta(hours=get_settings().token_ttl_hours)
    db.add(Enlace(expediente_id=item.id, rol=rol, token_hash=hash_token(token), expires_at=expires_at))
    registrar_evento(db, item.id, "enlace_generado", "gest2a3eco", {"rol": rol})
    return {
        "rol": rol,
        "url": f"{get_settings().public_base_url}/t/{item.referencia}/{rol}?token={token}",
        "expires_at": expires_at,
    }


def verificar_enlace(db: Session, referencia: str, rol: str, token: str) -> tuple[Expediente, Enlace]:
    if rol not in ROLES or not token:
        raise HTTPException(401, "Enlace no valido")
    stmt = (
        select(Enlace)
        .join(Expediente)
        .where(
            Expediente.referencia == referencia,
            Enlace.rol == rol,
            Enlace.token_hash == hash_token(token),
            Enlace.revoked_at.is_(None),
        )
        .order_by(Enlace.created_at.desc())
    )
    link = db.scalar(stmt)
    now = utcnow()
    if not link:
        raise HTTPException(401, "Enlace no valido")
    expires = link.expires_at
    if expires.tzinfo is None:
        expires = expires.replace(tzinfo=now.tzinfo)
    if expires <= now:
        raise HTTPException(401, "Enlace caducado")
    item = cargar_expediente(db, link.expediente_id)
    link.last_access_at = now
    return item, link


def registrar_evento(db: Session, expediente_id: str | None, tipo: str, actor: str, datos: dict | None = None):
    db.add(Evento(expediente_id=expediente_id, tipo=tipo, actor=actor, datos=datos or {}))
