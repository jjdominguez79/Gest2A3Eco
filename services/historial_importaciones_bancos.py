from __future__ import annotations

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
    for row in rows:
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
        movimientos.append((fecha, importe, saldo))

    movimientos.sort(key=lambda item: item[0])
    entradas = sum(importe for _, importe, _ in movimientos if importe > 0)
    salidas = sum(abs(importe) for _, importe, _ in movimientos if importe < 0)
    saldos = [(fecha, saldo) for fecha, _, saldo in movimientos if saldo is not None]
    return {
        "filas_leidas": len(rows),
        "movimientos_generados": len(movimientos),
        "movimientos_omitidos": max(0, len(rows) - len(movimientos)),
        "fecha_primer_asiento": movimientos[0][0] if movimientos else None,
        "fecha_ultimo_asiento": movimientos[-1][0] if movimientos else None,
        "saldo_primer_asiento": saldos[0][1] if saldos else None,
        "saldo_final": saldos[-1][1] if saldos else None,
        "importe_entradas": round(entradas, 2),
        "importe_salidas": round(salidas, 2),
        "variacion_neta": round(entradas - salidas, 2),
        "avisos": list(avisos or []),
    }
