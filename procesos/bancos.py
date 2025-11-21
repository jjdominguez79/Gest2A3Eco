# procesos/bancos.py
from typing import List, Dict, Any, Tuple
import fnmatch

from facturas_common import Linea, render_a3_tipo0_bancos, _fecha_yyyymmdd


def _fnum(x):
    """Convierte cualquier valor a float, aceptando coma o punto."""
    try:
        return float(str(x).replace(",", "."))
    except Exception:
        return 0.0


def generar_bancos(
    rows: List[Dict[str, Any]],
    plantilla: Dict[str, Any],
    codigo_empresa: str,
    ndig_plan: int
) -> Tuple[List[str], List[str]]:
    """
    Genera las líneas de suenlace para BANCOS (tipo 0) a partir de:
      - rows: filas mapeadas del Excel (con claves 'Fecha Asiento', 'Importe', 'Concepto', etc.)
      - plantilla: diccionario de configuración de la plantilla de bancos
      - codigo_empresa: código empresa A3 (string)
      - ndig_plan: nº de dígitos del plan contable de la empresa

    Devuelve:
      (lineas_DAT, avisos_fechas)

    avisos_fechas contendrá mensajes de filas donde la fecha no se ha podido
    interpretar y el movimiento se ha omitido.
    """
    sub_banco = str(plantilla.get("subcuenta_banco") or "").strip()
    sub_def   = str(plantilla.get("subcuenta_por_defecto") or "").strip()
    conceptos = plantilla.get("conceptos", [])

    if not sub_banco:
        raise ValueError("La plantilla de bancos no tiene 'Subcuenta banco'.")
    if not sub_def:
        raise ValueError("La plantilla de bancos no tiene 'Subcuenta por defecto'.")

    def subcuenta_por_concepto(txt: str) -> str:
        t = (str(txt) or "").lower()
        for cm in (conceptos or []):
            patron = (cm.get("patron", "*") or "*").lower()
            if fnmatch.fnmatch(t, patron):
                sub = (cm.get("subcuenta") or "").strip()
                if sub:
                    return sub
        return sub_def

    lineas: List[Linea] = []
    avisos: List[str] = []

    for idx, rec in enumerate(rows, start=1):
        # 1) Fecha: usamos las columnas habituales
        fecha_raw = (
            rec.get("Fecha Asiento")
            or rec.get("Fecha Operacion")
            or rec.get("Fecha Expedicion")
        )

        f8 = _fecha_yyyymmdd(fecha_raw)
        if f8 == "00000000":
            # No sabemos interpretar la fecha → omitimos el movimiento y avisamos
            avisos.append(
                f"Fila {idx}: fecha inválida '{fecha_raw}'. "
                f"Se omite el movimiento."
            )
            continue

        concepto_txt = (
            rec.get("Concepto")
            or rec.get("Descripcion Factura")
            or ""
        )
        val = _fnum(rec.get("Importe"))
        if val == 0:
            # Nada que contabilizar
            continue

        imp = abs(val)
        sub_contra = subcuenta_por_concepto(concepto_txt) or sub_def

        # Guardamos la fecha ya normalizada AAAAMMDD en la Linea
        # (render_a3_tipo0_bancos volverá a pasarla por _fecha_yyyymmdd, pero es idempotente)
        if val > 0:
            # + => Banco Debe, Contrapartida Haber
            lineas.append(Linea(f8, sub_banco,  "D", imp, str(concepto_txt)))
            lineas.append(Linea(f8, sub_contra, "H", imp, str(concepto_txt)))
        else:
            # - => Banco Haber, Contrapartida Debe
            lineas.append(Linea(f8, sub_contra, "D", imp, str(concepto_txt)))
            lineas.append(Linea(f8, sub_banco,  "H", imp, str(concepto_txt)))

    if not lineas:
        return [], avisos

    out_lines = render_a3_tipo0_bancos(lineas, codigo_empresa, ndig_plan=ndig_plan)
    return out_lines, avisos
