"""
Interpretacion de texto libre de facturas.

Responsabilidades:
  - Extraer NIF/CIF espanol, fechas, importes, numero de factura.
  - Detectar bases imponibles e IVA 21/10/4/0.
  - Detectar retenciones IRPF.
  - Calcular coherencia total = bases + IVA + recargo - retenciones.
  - Generar lista de errores de validacion si faltan campos esenciales.

Principios:
  - Sin dependencias de UI ni de base de datos.
  - Funciones puras testables de forma aislada.
  - Compatible con el contrato OcrInvoiceResult.
"""
from __future__ import annotations

import re
from typing import Optional

from services.ocr.types import OcrInvoiceResult, OcrVatLine, OcrRetentionLine

# ── Constantes ────────────────────────────────────────────────────────────────

TIPOS_IVA_ESPANA = {0.0, 4.0, 5.0, 10.0, 21.0}
TIPOS_RETENCION  = {1.0, 2.0, 7.0, 9.0, 15.0, 19.0, 24.0}
MIN_CHARS_TEXTO  = 30
TOLERANCIA_COHERENCIA = 0.10

MESES_ES = {
    "enero": 1, "febrero": 2, "marzo": 3, "abril": 4, "mayo": 5, "junio": 6,
    "julio": 7, "agosto": 8, "septiembre": 9, "octubre": 10, "noviembre": 11,
    "diciembre": 12,
    "ene": 1, "feb": 2, "mar": 3, "abr": 4, "may": 5, "jun": 6,
    "jul": 7, "ago": 8, "sep": 9, "oct": 10, "nov": 11, "dic": 12,
}


class InvoiceInterpreter:
    """
    Convierte texto libre extraido por OCR en un OcrInvoiceResult.

    Uso:
      result = InvoiceInterpreter().interpretar(texto)
    """

    def interpretar(self, texto: str) -> OcrInvoiceResult:
        """
        Procesa el texto y devuelve OcrInvoiceResult.

        Siempre devuelve un objeto valido (nunca lanza excepcion).
        """
        result = OcrInvoiceResult(texto=texto)
        t = texto.replace("\r", "\n")

        result.proveedor_nif    = _detectar_nif(t)
        result.proveedor_nombre = _detectar_nombre_proveedor(t)
        result.numero_factura   = _detectar_numero_factura(t)
        result.fecha_factura    = _detectar_fecha(t)
        result.fecha_vencimiento = _detectar_fecha_vencimiento(t)
        result.total            = _detectar_total(t)

        result.bases_iva   = _detectar_lineas_iva(t)
        result.retenciones = _detectar_retenciones(t)

        # Recalcular totales desde lineas si estan disponibles
        if result.bases_iva:
            result.recalcular_totales_desde_lineas()

        # Fallback: si no hay lineas pero hay texto de base/cuota
        if not result.bases_iva:
            linea = _linea_iva_fallback(t)
            if linea:
                result.bases_iva = [linea]
                result.base_total = linea.base
                result.iva_total  = linea.cuota_iva

        # Si total sigue en 0 pero hay base + iva, calcular
        if result.total == 0.0 and result.base_total:
            result.total = round(
                result.base_total + result.iva_total - result.retencion_total, 2
            )

        result.errores = self.generar_errores(result)
        return result

    def generar_errores(self, result: OcrInvoiceResult) -> list[str]:
        """Lista de errores de validacion (no necesariamente bloquean el flujo)."""
        errores = []
        if not result.proveedor_nif:
            errores.append("NIF/CIF del proveedor no detectado.")
        if not result.numero_factura:
            errores.append("Numero de factura no detectado.")
        if not result.fecha_factura:
            errores.append("Fecha de factura no detectada.")
        if result.total == 0.0:
            errores.append("Importe total no detectado o igual a cero.")
        if result.total and result.base_total and not result.coherente:
            esperado = round(result.base_total + result.iva_total - result.retencion_total, 2)
            errores.append(
                f"Importes incoherentes: base {result.base_total:.2f} + IVA {result.iva_total:.2f} "
                f"= {esperado:.2f} pero total = {result.total:.2f}."
            )
        return errores


# ── Deteccion de campos (funciones puras) ─────────────────────────────────────

def _detectar_nif(text: str) -> str:
    """Detecta NIF, CIF, NIE o VAT comunitario espanol."""
    _ETIQ = r"\b(?:CIF|NIF|VAT(?:[ \t]+(?:no\.?|number))?|N\.I\.F\.?|C\.I\.F\.)[ \t]*[:#\.]?[ \t]*"
    return _search(text, [
        _ETIQ + r"([A-Z]\d{7}[A-Z0-9])",    # CIF espanol con etiqueta
        _ETIQ + r"(\d{8}[A-Z])",              # NIF persona fisica con etiqueta
        _ETIQ + r"([XYZ]\d{7}[A-Z])",         # NIE con etiqueta
        _ETIQ + r"([A-Z]{2}[A-Z0-9]{2,13})",  # VAT comunitario con etiqueta
        r"\b([A-Z]\d{7}[A-Z0-9])\b",          # CIF sin etiqueta
        r"\b(\d{8}[A-Z])\b",                   # NIF persona fisica sin etiqueta
        r"\b([XYZ]\d{7}[A-Z])\b",              # NIE sin etiqueta
    ])


def _detectar_nombre_proveedor(text: str) -> str:
    """Heuristica: primera linea no vacia que no sea una etiqueta conocida."""
    skip = {
        "FACTURA", "INVOICE", "CIF", "NIF", "FECHA", "TOTAL", "BASE",
        "IVA", "ALBARAN", "PRESUPUESTO", "PEDIDO", "NOTA", "RECIBO", "ABONO",
        "ALBARÁN", "NÚMERO", "NUMERO", "PROVEEDOR", "CLIENTE",
    }
    for line in text.splitlines():
        clean = " ".join(line.split()).strip()
        if not clean or len(clean) < 3 or len(clean) > 80:
            continue
        upper = clean.upper()
        if any(tag in upper for tag in skip):
            continue
        if re.search(r"\d{1,2}[/\-]\d{1,2}[/\-]\d{2,4}", clean):
            continue
        if re.fullmatch(r"[\d\s\.,€$%\-/]+", clean):
            continue
        return clean
    return ""


def _detectar_numero_factura(text: str) -> str:
    """Detecta el numero de factura por patrones de etiqueta habituales."""
    return _search(text, [
        r"\b(?:Factura|Fra\.?|Invoice)\s*(?:N[ºo°]?\.?|No\.?|Num\.?|#)?\s*[:#\-]?\s*([A-Z0-9][A-Z0-9\/\.\-]{1,39})",
        r"\bN[ºo°]\s*(?:de\s+)?factura\s*[:#\-]?\s*([A-Z0-9][A-Z0-9\/\.\-]{1,39})",
        r"\b(?:Numero\s+de\s+documento|Ref(?:erencia)?\.?)\s*[:#]?\s*([A-Z0-9][A-Z0-9\/\.\-]{1,39})",
        r"\b(?:Serie|REF\.?)\s*[:#]?\s*([A-Z0-9][A-Z0-9\/\.\-]{1,39})",
    ])


def _detectar_fecha(text: str) -> str:
    """Extrae la fecha de factura, priorizando etiquetas explicitas."""
    # Con etiqueta explicita
    found = _search(text, [
        r"(?:Fecha\s+(?:de\s+)?(?:factura|emision|expedicion|emisi[oó]n)|"
        r"Invoice\s+date|Date)\s*[:#\-]?\s*"
        r"(\d{1,2}[\/\-\.]\d{1,2}[\/\-\.]\d{2,4}|\d{4}[\/\-\.]\d{1,2}[\/\-\.]\d{1,2})",
    ])
    if found:
        return _normalizar_fecha(found)

    # Con nombre de mes
    pat_mes = re.compile(
        r"(\d{1,2})\s+(?:de\s+)?(" + "|".join(MESES_ES.keys()) + r")\s+(?:de\s+)?(\d{4})",
        re.IGNORECASE,
    )
    m = pat_mes.search(text)
    if m:
        dia  = m.group(1).zfill(2)
        mes  = str(MESES_ES.get(m.group(2).lower(), 0)).zfill(2)
        ano  = m.group(3)
        return f"{ano}-{mes}-{dia}"

    # Fallback: primera fecha numerica
    m2 = re.search(
        r"\b(\d{1,2}[\/\-]\d{1,2}[\/\-]\d{4}|\d{4}[\/\-]\d{2}[\/\-]\d{2})\b",
        text,
    )
    return _normalizar_fecha(m2.group(1)) if m2 else ""


def _detectar_fecha_vencimiento(text: str) -> str:
    found = _search(text, [
        r"(?:Vencimiento|Fecha\s+vencimiento|Due\s+date|Vto\.?)\s*[:#\-]?\s*"
        r"(\d{1,2}[\/\-\.]\d{1,2}[\/\-\.]\d{2,4}|\d{4}[\/\-\.]\d{1,2}[\/\-\.]\d{1,2})",
    ])
    return _normalizar_fecha(found) if found else ""


def _detectar_total(text: str) -> float:
    return _buscar_importe(text, [
        r"\b(?:Total\s+(?:factura|importe|a\s+pagar)|Importe\s+total|TOTAL\s+FACTURA|TOTAL)\s*[:#\-]?\s*(?:EUR|€)?\s*([0-9][0-9\.,]*)",
        r"\b(?:Total\s+(?:factura|importe|a\s+pagar)|Importe\s+total|TOTAL\s+FACTURA|TOTAL)\s*[:#\-]?\s*([0-9][0-9\.,]*)\s*(?:EUR|€)?",
    ])


# ── Deteccion de lineas de IVA ────────────────────────────────────────────────

def _detectar_lineas_iva(text: str) -> list[OcrVatLine]:
    """Intenta varios patrones para detectar tramos de IVA multiples."""
    lineas = _detectar_tabla_iva(text)
    if not lineas:
        lineas = _detectar_pares_tipo_iva(text)
    if not lineas:
        lineas = _detectar_iva_junto_a_base(text)
    return lineas


def _detectar_tabla_iva(text: str) -> list[OcrVatLine]:
    """
    Detecta filas de tabla con patron: TIPO%  BASE  CUOTA_IVA
    Ejemplo: 21%  1.000,00  210,00
    """
    patron = re.compile(
        r"(\d{1,2}(?:[,\.]\d+)?)\s*%\s+([0-9][0-9\.,]*)\s+([0-9][0-9\.,]*)",
        re.IGNORECASE,
    )
    lineas: list[OcrVatLine] = []
    for m in patron.finditer(text):
        tipo  = _parse_amount(m.group(1))
        base  = _parse_amount(m.group(2))
        cuota = _parse_amount(m.group(3))
        if 0.0 <= tipo <= 100.0 and base > 0:
            lineas.append(OcrVatLine(tipo_iva=tipo, base=base, cuota_iva=cuota))
    return lineas


def _detectar_pares_tipo_iva(text: str) -> list[OcrVatLine]:
    """
    Detecta pares explicitos:
      'Base al 21%: 1.000,00'  +  'Cuota IVA 21%: 210,00'
    """
    pat_base  = re.compile(
        r"(?:Base\s+(?:imponible\s+)?(?:al\s+)?|Base\s*)(\d{1,2}(?:[,\.]\d+)?)\s*%\s*[:#]?\s*([0-9][0-9\.,]*)",
        re.IGNORECASE,
    )
    pat_cuota = re.compile(
        r"(?:Cuota\s+IVA?|IVA?)\s+(?:al\s+)?(\d{1,2}(?:[,\.]\d+)?)\s*%\s*[:#]?\s*([0-9][0-9\.,]*)",
        re.IGNORECASE,
    )
    bases:  dict[float, float] = {}
    cuotas: dict[float, float] = {}
    for m in pat_base.finditer(text):
        tipo  = _parse_amount(m.group(1))
        valor = _parse_amount(m.group(2))
        if 0.0 <= tipo <= 100.0 and valor > 0:
            bases[tipo] = valor
    for m in pat_cuota.finditer(text):
        tipo  = _parse_amount(m.group(1))
        valor = _parse_amount(m.group(2))
        if 0.0 <= tipo <= 100.0 and valor > 0:
            cuotas[tipo] = valor
    todos_tipos = sorted(set(list(bases) + list(cuotas)))
    lineas = []
    for tipo in todos_tipos:
        base  = bases.get(tipo, 0.0)
        cuota = cuotas.get(tipo, 0.0)
        if base > 0 or cuota > 0:
            lineas.append(OcrVatLine(tipo_iva=tipo, base=base, cuota_iva=cuota))
    return lineas


def _detectar_iva_junto_a_base(text: str) -> list[OcrVatLine]:
    """
    Detecta patron 'IVA (21%): 210,00' junto a 'Base imponible: 1.000,00'.
    """
    pat = re.compile(
        r"IVA\s*\((\d{1,2})\s*%\)\s*[:#]?\s*([0-9][0-9\.,]*)",
        re.IGNORECASE,
    )
    lineas = []
    for m in pat.finditer(text):
        tipo  = _parse_amount(m.group(1))
        cuota = _parse_amount(m.group(2))
        # Intentar encontrar base correspondiente
        base = _buscar_importe(text, [
            r"\b(?:Base\s+imponible|Base)\s*[:#]?\s*([0-9][0-9\.,]*)",
        ])
        if cuota > 0:
            lineas.append(OcrVatLine(tipo_iva=tipo, base=base, cuota_iva=cuota))
    return lineas


def _linea_iva_fallback(text: str) -> Optional[OcrVatLine]:
    """Linea unica con importes globales (sin tipo de IVA explicito)."""
    base  = _buscar_importe(text, [
        r"\b(?:Base\s+imponible|Base)\s*[:#]?\s*([0-9][0-9\.,]*)",
    ])
    cuota = _buscar_importe(text, [
        r"\b(?:Cuota\s+IVA?|IVA?)\s*[:#]?\s*([0-9][0-9\.,]*)",
    ])
    if base or cuota:
        tipo = round(cuota / base * 100, 1) if base else 0.0
        # Ajustar a tipo standard si es aproximado
        for t in sorted(TIPOS_IVA_ESPANA, reverse=True):
            if abs(tipo - t) <= 1.5:
                tipo = t
                break
        return OcrVatLine(tipo_iva=tipo, base=base, cuota_iva=cuota)
    return None


# ── Deteccion de retenciones ──────────────────────────────────────────────────

def _detectar_retenciones(text: str) -> list[OcrRetentionLine]:
    """
    Detecta retenciones IRPF por patrones habituales:
      'Retencion IRPF 15%: -150,00'
      'IRPF (15%): 150,00'
      'Retencion: 150,00'
    """
    pat_con_tipo = re.compile(
        r"(?:Retenci[oó]n\s+IRPF|IRPF)\s*\(?\s*(\d{1,2}(?:[,\.]\d+)?)\s*%\)?\s*[:#\-]?\s*-?\s*([0-9][0-9\.,]*)",
        re.IGNORECASE,
    )
    pat_sin_tipo = re.compile(
        r"\b(?:Retenci[oó]n|R\.\s*IRPF)\s*[:#]?\s*-?\s*([0-9][0-9\.,]*)",
        re.IGNORECASE,
    )

    retenciones: list[OcrRetentionLine] = []
    for m in pat_con_tipo.finditer(text):
        tipo    = _parse_amount(m.group(1))
        importe = _parse_amount(m.group(2))
        if importe > 0:
            base = round(importe / tipo * 100, 2) if tipo else 0.0
            retenciones.append(OcrRetentionLine(
                tipo_retencion=tipo,
                importe_retencion=importe,
                base_retencion=base,
            ))

    if not retenciones:
        for m in pat_sin_tipo.finditer(text):
            importe = _parse_amount(m.group(1))
            if importe > 0:
                retenciones.append(OcrRetentionLine(importe_retencion=importe))

    return retenciones


# ── Utilidades de parsing ─────────────────────────────────────────────────────

def _search(text: str, patterns: list[str]) -> str:
    for pat in patterns:
        m = re.search(pat, text, flags=re.IGNORECASE)
        if m:
            return str(m.group(1)).strip()
    return ""


def _parse_amount(raw: str) -> float:
    """
    Convierte importes en formato espanol o ingles a float.

    Logica:
      '1.234,56' → 1234.56  (miles=punto, decimal=coma)
      '1,234.56' → 1234.56  (miles=coma, decimal=punto)
      '1234,56'  → 1234.56  (sin miles, decimal=coma)
      '1234.56'  → 1234.56  (sin miles, decimal=punto)
      '1.234'    → 1234.0   (solo miles)
    """
    s = str(raw or "").strip().replace("€", "").replace("$", "").strip()
    if not s:
        return 0.0
    if "," in s and "." in s:
        if s.rfind(",") > s.rfind("."):
            s = s.replace(".", "").replace(",", ".")
        else:
            s = s.replace(",", "")
    elif "," in s:
        partes = s.split(",")
        if len(partes) == 2 and len(partes[1]) <= 2:
            s = s.replace(",", ".")
        else:
            s = s.replace(",", "")
    elif "." in s:
        partes = s.split(".")
        if len(partes) > 1 and len(partes[-1]) == 3:
            s = s.replace(".", "")
    try:
        return round(float(s), 2)
    except Exception:
        return 0.0


def _buscar_importe(text: str, patterns: list[str]) -> float:
    return _parse_amount(_search(text, patterns))


def _normalizar_fecha(raw: str) -> str:
    """Intenta convertir varios formatos a YYYY-MM-DD."""
    if not raw:
        return ""
    raw = raw.strip()
    # YYYY-MM-DD ya correcto
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", raw):
        return raw
    # DD/MM/YYYY o DD-MM-YYYY o DD.MM.YYYY
    m = re.fullmatch(r"(\d{1,2})[/\-\.](\d{1,2})[/\-\.](\d{4})", raw)
    if m:
        return f"{m.group(3)}-{m.group(2).zfill(2)}-{m.group(1).zfill(2)}"
    # YYYY/MM/DD
    m = re.fullmatch(r"(\d{4})[/\-\.](\d{1,2})[/\-\.](\d{1,2})", raw)
    if m:
        return f"{m.group(1)}-{m.group(2).zfill(2)}-{m.group(3).zfill(2)}"
    return raw
