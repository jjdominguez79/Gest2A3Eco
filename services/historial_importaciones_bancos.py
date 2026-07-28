from __future__ import annotations

import hashlib
import re
import unicodedata
from collections import Counter

from models.facturas_common import _fecha_yyyymmdd


def _numero(valor):
    if valor is None or str(valor).strip().lower() in ("", "nan"):
        return None
    try:
        texto = str(valor).strip().replace(" ", "")
        if "," in texto and "." in texto:
            texto = texto.replace(".", "").replace(",", ".")
        else:
            texto = texto.replace(",", ".")
        return float(texto)
    except (TypeError, ValueError):
        return None


def resumir_importacion_banco(rows: list[dict], avisos: list[str]) -> dict:
    """Calcula magnitudes auditables usando solo movimientos contabilizables."""
    movimientos = []
    for orden, row in enumerate(rows):
        fecha = _fecha_yyyymmdd(
            row.get("Fecha Asiento")
            or row.get("Fecha Operacion")
            or row.get("Fecha Expedicion")
        )
        importe = _numero(row.get("Importe"))
        if fecha == "00000000" or importe in (None, 0):
            continue
        saldo = next(
            (_numero(row.get(k)) for k in ("Saldo", "Saldo banco", "Saldo Banco", "Saldo disponible")
             if _numero(row.get(k)) is not None),
            None,
        )
        movimientos.append((fecha, importe, saldo, orden))

    movimientos.sort(key=lambda item: (item[0], item[3]))
    entradas = sum(importe for _, importe, _, _ in movimientos if importe > 0)
    salidas = sum(abs(importe) for _, importe, _, _ in movimientos if importe < 0)
    saldos = [
        (fecha, saldo, orden)
        for fecha, _, saldo, orden in movimientos if saldo is not None
    ]
    fecha_final = movimientos[-1][0] if movimientos else None
    saldo_final = _saldo_cierre_fecha(movimientos, fecha_final)
    return {
        "filas_leidas": len(rows),
        "movimientos_generados": len(movimientos),
        "movimientos_omitidos": max(0, len(rows) - len(movimientos)),
        "fecha_primer_asiento": movimientos[0][0] if movimientos else None,
        "fecha_ultimo_asiento": movimientos[-1][0] if movimientos else None,
        "saldo_primer_asiento": saldos[0][1] if saldos else None,
        "saldo_final": saldo_final,
        "importe_entradas": round(entradas, 2),
        "importe_salidas": round(salidas, 2),
        "variacion_neta": round(entradas - salidas, 2),
        "avisos": list(avisos or []),
    }


def normalizar_movimientos_banco(rows: list[dict]) -> list[dict]:
    """Convierte filas Excel en movimientos comparables y asigna ocurrencias."""
    movimientos = []
    ocurrencias = Counter()
    for indice, row in enumerate(rows or []):
        fecha = _fecha_yyyymmdd(
            row.get("Fecha Asiento")
            or row.get("Fecha Operacion")
            or row.get("Fecha Expedicion")
        )
        importe = _numero(row.get("Importe"))
        if fecha == "00000000" or importe in (None, 0):
            continue
        concepto = str(
            row.get("Concepto") or row.get("Descripcion Factura") or ""
        ).strip()
        referencia = _primero_con_valor(
            row,
            (
                "Referencia", "Referencia bancaria", "Referencia Bancaria",
                "Numero movimiento", "Número movimiento", "Documento",
            ),
        )
        saldo = _primero_numero(
            row, ("Saldo", "Saldo banco", "Saldo Banco", "Saldo disponible")
        )
        base = "|".join((
            fecha,
            f"{importe:.2f}",
            _texto_huella(concepto),
            _texto_huella(referencia),
        ))
        huella = hashlib.sha256(base.encode("utf-8")).hexdigest()
        ocurrencias[huella] += 1
        movimientos.append({
            "indice_fila": indice,
            "fecha": fecha,
            "importe": importe,
            "concepto": concepto,
            "referencia": referencia,
            "saldo": saldo,
            "huella": huella,
            "ocurrencia": ocurrencias[huella],
        })
    return movimientos


def analizar_duplicados_banco(
    rows: list[dict],
    movimientos_anteriores: list[dict],
    importaciones_solapadas: list[dict] | None = None,
) -> dict:
    """Clasifica filas nuevas, repetidas y posiblemente modificadas."""
    actuales = normalizar_movimientos_banco(rows)
    claves_anteriores = {
        (str(m.get("huella") or ""), int(m.get("ocurrencia") or 1))
        for m in movimientos_anteriores or []
    }
    referencias_anteriores = {
        (str(m.get("fecha") or ""), _texto_huella(m.get("referencia"))):
        str(m.get("huella") or "")
        for m in movimientos_anteriores or []
        if _texto_huella(m.get("referencia"))
    }
    nuevos, duplicados, modificados = [], [], []
    for movimiento in actuales:
        clave = (movimiento["huella"], movimiento["ocurrencia"])
        clave_ref = (
            movimiento["fecha"], _texto_huella(movimiento["referencia"])
        )
        if clave in claves_anteriores:
            duplicados.append(movimiento)
        elif (
            clave_ref[1]
            and clave_ref in referencias_anteriores
            and referencias_anteriores[clave_ref] != movimiento["huella"]
        ):
            modificados.append(movimiento)
        else:
            nuevos.append(movimiento)

    return {
        "movimientos": actuales,
        "nuevos": nuevos,
        "duplicados": duplicados,
        "modificados": modificados,
        "importaciones_solapadas": list(importaciones_solapadas or []),
        "fecha_desde": min((m["fecha"] for m in actuales), default=None),
        "fecha_hasta": max((m["fecha"] for m in actuales), default=None),
        "hay_conflicto": bool(
            duplicados or modificados or importaciones_solapadas
        ),
    }


def _texto_huella(valor) -> str:
    texto = unicodedata.normalize("NFKD", str(valor or ""))
    texto = "".join(ch for ch in texto if not unicodedata.combining(ch))
    return re.sub(r"\s+", " ", texto).strip().upper()


def _primero_con_valor(row: dict, claves) -> str:
    for clave in claves:
        valor = row.get(clave)
        if valor is not None and str(valor).strip().lower() not in ("", "nan"):
            return str(valor).strip()
    return ""


def _primero_numero(row: dict, claves):
    for clave in claves:
        numero = _numero(row.get(clave))
        if numero is not None:
            return numero
    return None


def _saldo_cierre_fecha(movimientos, fecha):
    """
    Obtiene el saldo posterior al ultimo movimiento del dia aunque el extracto
    ordene las operaciones de ese dia en sentido ascendente o descendente.

    Para ello enlaza saldos consecutivos: saldo_siguiente = saldo_actual +
    importe_siguiente. El saldo sin sucesor es el cierre del dia.
    """
    dia = [
        (importe, saldo, orden)
        for f, importe, saldo, orden in movimientos
        if f == fecha and saldo is not None
    ]
    if not dia:
        return None
    if len(dia) == 1:
        return dia[0][1]

    tiene_sucesor = set()
    for idx, (_importe, saldo, _orden) in enumerate(dia):
        for otro_idx, (otro_importe, otro_saldo, _otro_orden) in enumerate(dia):
            if idx == otro_idx:
                continue
            if abs((saldo + otro_importe) - otro_saldo) <= 0.01:
                tiene_sucesor.add(idx)
                break
    finales = [item for idx, item in enumerate(dia) if idx not in tiene_sucesor]
    if len(finales) == 1:
        return finales[0][1]
    # Extractos sin una cadena de saldos reconocible: conservar el orden fuente.
    return max(dia, key=lambda item: item[2])[1]
