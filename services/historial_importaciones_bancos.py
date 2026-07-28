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
