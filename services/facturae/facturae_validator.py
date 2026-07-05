from __future__ import annotations

from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP
from xml.etree import ElementTree as ET

from services.facturae.facturae_codes import FACTURAE_NS, FACTURAE_STATUS_ERROR_VALIDACION


Q2 = Decimal("0.01")


def d2(value) -> Decimal:
    return Decimal(str(value or 0)).quantize(Q2, rounding=ROUND_HALF_UP)


def validate_facturae_payload(payload: dict) -> list[str]:
    errors: list[str] = []
    factura = payload["factura"]
    emisor = payload["emisor"]
    receptor = payload["receptor"]
    rel = payload.get("relacion_tercero") or {}

    for label, party in (("emisor", emisor), ("receptor", receptor)):
        if not str(party.get("nombre") or "").strip():
            errors.append(f"Falta el nombre o razon social del {label}.")
        if not str(party.get("nif") or "").strip():
            errors.append(f"Falta el NIF/CIF del {label}.")
        if not str(party.get("direccion") or "").strip():
            errors.append(f"Falta la direccion del {label}.")
        if not str(party.get("cp") or "").strip():
            errors.append(f"Falta el codigo postal del {label}.")
        if not str(party.get("poblacion") or "").strip():
            errors.append(f"Falta el municipio/poblacion del {label}.")
        if not str(party.get("provincia") or "").strip():
            errors.append(f"Falta la provincia del {label}.")
        if not str(party.get("pais") or "").strip():
            errors.append(f"Falta el pais del {label}.")

    if str(factura.get("moneda_codigo") or "EUR").strip().upper() != "EUR":
        errors.append("Solo se soporta moneda EUR en la primera fase de Facturae.")
    if not str(factura.get("fecha_expedicion") or factura.get("fecha_asiento") or "").strip():
        errors.append("La factura no tiene fecha de expedicion.")
    if not str(factura.get("numero") or "").strip():
        errors.append("La factura no tiene numero.")

    lineas_validas = list(payload.get("lineas") or [])
    if not lineas_validas:
        errors.append("La factura debe tener al menos una linea.")

    total_base = Decimal("0.00")
    total_iva = Decimal("0.00")
    total_ret = Decimal("0.00")
    total_factura = d2(payload["totales"]["total"])
    for index, linea in enumerate(lineas_validas, start=1):
        base = d2(linea.get("base"))
        iva = d2(linea.get("cuota_iva"))
        ret = d2(linea.get("cuota_irpf"))
        pct_iva = d2(linea.get("pct_iva"))
        total_base += base
        total_iva += iva
        total_ret += ret
        if base < 0 and payload["invoice_class"] != "OR":
            errors.append(f"La linea {index} tiene base negativa y la factura no es rectificativa.")
        if not str(linea.get("concepto") or "").strip():
            errors.append(f"La linea {index} no tiene descripcion.")
        expected_iva = (base * pct_iva / Decimal("100")).quantize(Q2, rounding=ROUND_HALF_UP)
        if expected_iva != iva:
            errors.append(
                f"La linea {index} tiene descuadre entre base, tipo de IVA y cuota de IVA."
            )
        try:
            qty = Decimal(str(linea.get("unidades") or 0))
        except Exception:
            qty = Decimal("0")
        if qty <= 0:
            errors.append(f"La linea {index} debe tener cantidad positiva.")

    expected_total = (total_base + total_iva - total_ret).quantize(Q2, rounding=ROUND_HALF_UP)
    if expected_total != total_factura:
        errors.append(
            f"El total de factura no cuadra: esperado {expected_total} y calculado {total_factura}."
        )

    if rel.get("facturae_es_administracion_publica"):
        for key, label in (
            ("facturae_dir3_oficina_contable", "Oficina contable DIR3"),
            ("facturae_dir3_organo_gestor", "Organo gestor DIR3"),
            ("facturae_dir3_unidad_tramitadora", "Unidad tramitadora DIR3"),
        ):
            if not str(rel.get(key) or "").strip():
                errors.append(f"Falta {label} para cliente de Administracion Publica.")

    if payload.get("corrective") is not None and not str(payload["corrective"].get("reason_code") or "").strip():
        errors.append("La factura rectificativa requiere codigo de motivo.")

    return errors


def validate_facturae_xml_content(xml_content: str) -> list[str]:
    errors: list[str] = []
    try:
        root = ET.fromstring(xml_content)
    except ET.ParseError as exc:
        return [f"El XML Facturae generado no es valido: {exc}"]
    if not root.tag.endswith("Facturae"):
        errors.append("La raiz del XML no es Facturae.")
    if FACTURAE_NS not in root.tag:
        errors.append("El namespace principal de Facturae no coincide con 3.2.2.")
    return errors


def build_facturae_error_payload(errors: list[str]) -> dict:
    return {
        "facturae_status": FACTURAE_STATUS_ERROR_VALIDACION,
        "facturae_error": "\n".join(errors),
        "facturae_generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }
