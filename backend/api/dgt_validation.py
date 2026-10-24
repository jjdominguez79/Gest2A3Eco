"""Comprobacion no destructiva de los datos de un expediente DGT."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.api.models import Documento, Expediente
from backend.api.validation import validar_parte


def comprobar_expediente(db: Session, item: Expediente) -> dict:
    """Devuelve el mismo checklist funcional usado antes de validar el tramite."""
    resultado_partes: dict[str, dict] = {}
    errores_globales: list[str] = []

    for rol in ("vendedor", "comprador"):
        parte = next((actual for actual in item.partes if actual.rol == rol), None)
        errores: list[str] = []
        estado = parte.estado if parte else "pendiente"
        if parte is None:
            errores.append(f"No existen los datos del {rol}.")
        else:
            if parte.estado != "completado":
                errores.append(f"El {rol} todavia no ha enviado el formulario completo.")
            errores.extend(validar_parte(parte, rol))
            if rol == "vendedor" and parte.tipo_persona == "juridica":
                tiene_factura = bool(
                    db.scalar(
                        select(Documento.id)
                        .where(
                            Documento.expediente_id == item.id,
                            Documento.rol == "vendedor",
                            Documento.tipo == "factura",
                        )
                        .limit(1)
                    )
                )
                if not tiene_factura:
                    errores.append("La factura del vendedor juridico es obligatoria.")

        resultado_partes[rol] = {
            "estado": estado,
            "completo": not errores,
            "errores": errores,
        }
        errores_globales.extend(
            f"{rol.capitalize()}: {error}" for error in errores
        )

    operacion = item.operacion.datos if item.operacion else {}
    modelo_620_necesario = bool((operacion or {}).get("modelo_620_presentado"))
    modelo_620_aportado = bool(
        db.scalar(
            select(Documento.id)
            .where(
                Documento.expediente_id == item.id,
                Documento.tipo == "modelo_620",
            )
            .limit(1)
        )
    )
    if modelo_620_necesario and not modelo_620_aportado:
        errores_globales.append("Debes adjuntar el modelo 620 presentado.")

    return {
        "expediente_id": item.id,
        "referencia": item.referencia,
        "completo": not errores_globales,
        "partes": resultado_partes,
        "documentacion": {
            "modelo_620_necesario": modelo_620_necesario,
            "modelo_620_aportado": modelo_620_aportado,
        },
        "errores": errores_globales,
    }
