"""Gestion movil de expedientes DGT para administradores autenticados."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from backend.api.database import get_db
from backend.api.dgt_validation import comprobar_expediente
from backend.api.messaging_api import require_messaging_staff
from backend.api.messaging_models import MessagingStaff
from backend.api.models import Expediente
from backend.api.schemas import ExpedienteCreate
from backend.api.service import (
    cargar_expediente,
    crear_enlace,
    crear_expediente,
    serializar_expediente,
)


router = APIRouter(
    prefix="/api/v1/messaging/staff/dgt",
    tags=["staff-dgt"],
)


def _operador_dgt(
    staff: MessagingStaff = Depends(require_messaging_staff),
) -> MessagingStaff:
    if staff.review_only or staff.role != "admin":
        raise HTTPException(403, "Usuario no autorizado para gestionar tramites DGT")
    return staff


def _resumen(item: Expediente) -> dict:
    return serializar_expediente(item)


@router.get("/expedientes")
def listar_expedientes_dgt(
    _staff: MessagingStaff = Depends(_operador_dgt),
    db: Session = Depends(get_db),
):
    stmt = (
        select(Expediente)
        .options(
            selectinload(Expediente.partes),
            selectinload(Expediente.vehiculo),
            selectinload(Expediente.operacion),
        )
        .order_by(Expediente.updated_at.desc())
    )
    return [_resumen(item) for item in db.scalars(stmt).unique()]


@router.post("/expedientes", status_code=201)
def crear_expediente_dgt(
    payload: ExpedienteCreate,
    staff: MessagingStaff = Depends(_operador_dgt),
    db: Session = Depends(get_db),
):
    item = crear_expediente(db, payload, actor=staff.external_id)
    links = {
        rol: crear_enlace(db, item, rol, actor=staff.external_id)
        for rol in ("vendedor", "comprador")
    }
    item.estado = "enlaces_enviados"
    db.commit()
    return {
        "expediente": _resumen(cargar_expediente(db, item.id)),
        "enlaces": links,
    }


@router.get("/expedientes/{expediente_id}")
def detalle_expediente_dgt(
    expediente_id: str,
    _staff: MessagingStaff = Depends(_operador_dgt),
    db: Session = Depends(get_db),
):
    return _resumen(cargar_expediente(db, expediente_id))


@router.post("/expedientes/{expediente_id}/enlaces")
def generar_enlaces_dgt(
    expediente_id: str,
    staff: MessagingStaff = Depends(_operador_dgt),
    db: Session = Depends(get_db),
):
    item = cargar_expediente(db, expediente_id)
    if item.estado == "terminado":
        raise HTTPException(409, "El expediente esta terminado")
    links = {
        rol: crear_enlace(db, item, rol, actor=staff.external_id)
        for rol in ("vendedor", "comprador")
    }
    item.estado = "enlaces_enviados"
    db.commit()
    return links


@router.get("/expedientes/{expediente_id}/comprobacion")
def comprobar_expediente_dgt(
    expediente_id: str,
    _staff: MessagingStaff = Depends(_operador_dgt),
    db: Session = Depends(get_db),
):
    return comprobar_expediente(db, cargar_expediente(db, expediente_id))
