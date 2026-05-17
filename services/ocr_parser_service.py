"""
Parsing y validacion de texto OCR de facturas.

Responsabilidades:
  - Extraer campos estructurados del texto libre devuelto por el motor OCR.
  - Detectar multiples tramos de IVA (bases imponibles separadas por tipo).
  - Clasificar el documento: pendiente_revision o error.
  - Generar avisos no bloqueantes sin ocultar nada al usuario.

Principios de diseno:
  - Sin dependencias de UI ni de base de datos.
  - Funciones puras testables de forma aislada.
  - Conservador: ante la duda, aviso en lugar de descarte silencioso.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field


# ── Modelos de resultado ──────────────────────────────────────────────────────

@dataclass
class LineaFiscalParseada:
    tipo_iva: float = 0.0
    base_imponible: float = 0.0
    cuota_iva: float = 0.0
    tipo_recargo: float = 0.0
    cuota_recargo: float = 0.0
    tipo_retencion: float = 0.0
    cuota_retencion: float = 0.0


@dataclass
class ParseResult:
    proveedor_nif: str = ""
    proveedor_nombre: str = ""
    numero_factura: str = ""
    fecha_factura: str = ""
    fecha_operacion: str = ""
    fecha_asiento: str = ""
    descripcion: str = ""
    moneda_codigo: str = "EUR"
    total: float = 0.0
    lineas_fiscales: list[LineaFiscalParseada] = field(default_factory=list)
    avisos: list[str] = field(default_factory=list)
    errores_criticos: list[str] = field(default_factory=list)
    # "pendiente_revision" | "error"
    bandeja: str = "pendiente_revision"

    # ── Agregados calculados ──────────────────────────────────────────────────

    @property
    def base_imponible(self) -> float:
        return _sum_field(self.lineas_fiscales, "base_imponible")

    @property
    def cuota_iva(self) -> float:
        return _sum_field(self.lineas_fiscales, "cuota_iva")

    @property
    def cuota_recargo(self) -> float:
        return _sum_field(self.lineas_fiscales, "cuota_recargo")

    @property
    def cuota_retencion(self) -> float:
        return _sum_field(self.lineas_fiscales, "cuota_retencion")

    # ── Conversion al formato dict que espera el controlador ─────────────────

    def to_legacy_dict(self) -> dict:
        """Convierte a formato identico al que devuelvia OCRService antes de Fase 4."""
        return {
            "proveedor_nif": self.proveedor_nif,
            "proveedor_nombre": self.proveedor_nombre,
            "numero_factura": self.numero_factura,
            "fecha_factura": self.fecha_factura,
            "fecha_operacion": self.fecha_operacion,
            "fecha_asiento": self.fecha_asiento,
            "descripcion": self.descripcion,
            "moneda_codigo": self.moneda_codigo,
            "base_imponible": self.base_imponible,
            "cuota_iva": self.cuota_iva,
            "cuota_recargo": self.cuota_recargo,
            "cuota_retencion": self.cuota_retencion,
            "total": self.total,
            "lineas": [
                {
                    "tipo_iva": l.tipo_iva,
                    "base": l.base_imponible,
                    "cuota_iva": l.cuota_iva,
                    "tipo_recargo": l.tipo_recargo,
                    "cuota_re": l.cuota_recargo,       # clave legacy usada por procesos/
                    "cuota_irpf": l.cuota_retencion,   # clave legacy
                    "cuota_retencion": l.cuota_retencion,
                    "descripcion": self.descripcion,
                }
                for l in self.lineas_fiscales
            ],
            "avisos": self.avisos + self.errores_criticos,
            "datos_extra": {},
            # Campos nuevos Fase 4
            "bandeja": self.bandeja,
            "error_mensaje": "; ".join(self.errores_criticos) if self.errores_criticos else "",
        }


# ── Servicio principal ────────────────────────────────────────────────────────

class OcrParserService:
    """Parsea texto OCR en un ParseResult validado y clasificado."""

    TOLERANCIA_REDONDEO = 0.05
    TIPOS_IVA_ESPANA = {0.0, 4.0, 5.0, 10.0, 21.0}  # para detectar candidatos falsos

    def __init__(self, tolerancia_redondeo: float | None = None):
        self._tol = tolerancia_redondeo if tolerancia_redondeo is not None else self.TOLERANCIA_REDONDEO

    # ── Punto de entrada ──────────────────────────────────────────────────────

    def parsear_y_validar(self, texto: str) -> ParseResult:
        result = self._parsear(texto)
        self._validar_y_clasificar(result)
        return result

    # ── Parsing ───────────────────────────────────────────────────────────────

    def _parsear(self, texto: str) -> ParseResult:
        t = texto.replace("\r", "\n")
        r = ParseResult()

        r.proveedor_nif     = _detectar_nif(t)
        r.proveedor_nombre  = _detectar_nombre_proveedor(t)
        r.numero_factura    = _detectar_numero_factura(t)
        r.fecha_factura     = _detectar_fecha(t)
        r.fecha_operacion   = r.fecha_factura
        r.fecha_asiento     = r.fecha_factura
        r.total             = _detectar_total(t)

        r.lineas_fiscales = self._detectar_lineas_fiscales(t)
        if not r.lineas_fiscales:
            r.lineas_fiscales = self._linea_fallback(t)

        if r.total == 0.0 and r.base_imponible:
            r.total = round(r.base_imponible + r.cuota_iva, 2)

        r.descripcion = _construir_descripcion(r)
        return r

    # ── Validacion ────────────────────────────────────────────────────────────

    def _validar_y_clasificar(self, r: ParseResult):
        if not r.proveedor_nif:
            r.errores_criticos.append("NIF no detectado.")
        if not r.numero_factura:
            r.errores_criticos.append("Numero de factura no detectado.")
        if not r.fecha_factura:
            r.avisos.append("Fecha de factura no detectada.")
        if r.total == 0.0:
            r.avisos.append("Importe total no detectado o igual a cero.")

        if r.total and r.base_imponible:
            esperado = round(r.base_imponible + r.cuota_iva - r.cuota_retencion, 2)
            diff = abs(r.total - esperado)
            if diff > self._tol:
                r.avisos.append(
                    f"Importes incoherentes: base {r.base_imponible:.2f} + IVA {r.cuota_iva:.2f} "
                    f"= {esperado:.2f}, pero total detectado = {r.total:.2f} "
                    f"(diferencia {diff:.2f})."
                )

        r.bandeja = "error" if r.errores_criticos else "pendiente_revision"

    # ── Deteccion multi-base ──────────────────────────────────────────────────

    def _detectar_lineas_fiscales(self, text: str) -> list[LineaFiscalParseada]:
        lineas = _detectar_tabla_iva(text)
        if not lineas:
            lineas = _detectar_pares_tipo_iva(text)
        return lineas

    def _linea_fallback(self, text: str) -> list[LineaFiscalParseada]:
        """Una sola linea con los importes globales del documento."""
        base = _buscar_importe(text, [
            r"\b(?:Base\s+imponible|Base)\s*[:#]?\s*([0-9][0-9\.,]*)",
        ])
        cuota = _buscar_importe(text, [
            r"\b(?:Cuota\s+IVA?|IVA?)\s*[:#]?\s*([0-9][0-9\.,]*)",
        ])
        if base or cuota:
            return [LineaFiscalParseada(base_imponible=base, cuota_iva=cuota)]
        return []


# ── Deteccion multi-base (funciones puras testables) ─────────────────────────

def _detectar_tabla_iva(text: str) -> list[LineaFiscalParseada]:
    """
    Detecta filas de tabla con patron:  TIPO%   BASE   CUOTA
    Ejemplo:
      21%   1.000,00   210,00
      10%     500,00    50,00
    Solo acepta tipos de IVA entre 0 y 100.
    """
    patron = re.compile(
        r"(\d{1,2}(?:[,\.]\d+)?)\s*%\s+([0-9][0-9\.,]*)\s+([0-9][0-9\.,]*)",
        re.IGNORECASE,
    )
    lineas: list[LineaFiscalParseada] = []
    for m in patron.finditer(text):
        tipo  = _parse_amount(m.group(1))
        base  = _parse_amount(m.group(2))
        cuota = _parse_amount(m.group(3))
        if 0.0 <= tipo <= 100.0 and base > 0:
            lineas.append(LineaFiscalParseada(tipo_iva=tipo, base_imponible=base, cuota_iva=cuota))
    return lineas


def _detectar_pares_tipo_iva(text: str) -> list[LineaFiscalParseada]:
    """
    Detecta pares explicitos:
      'Base al 21%: 1.000,00'  y  'Cuota IVA 21%: 210,00'
      'IVA 21% 210,00'
    """
    pat_base = re.compile(
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
            lineas.append(LineaFiscalParseada(tipo_iva=tipo, base_imponible=base, cuota_iva=cuota))
    return lineas


# ── Deteccion de campos individuales (funciones puras) ────────────────────────

def _detectar_nif(text: str) -> str:
    # Etiqueta en la misma linea (sin cruzar \n): separador solo espacios/tabuladores
    _ETIQ = r"\b(?:CIF|NIF|VAT(?:[ \t]+(?:no\.?|number))?|N\.I\.F\.?|C\.I\.F\.)[ \t]*[:#\.]?[ \t]*"
    return _search(text, [
        _ETIQ + r"([A-Z]\d{7}[A-Z0-9])",    # CIF espanol con etiqueta
        _ETIQ + r"(\d{8}[A-Z])",              # NIF persona fisica con etiqueta
        _ETIQ + r"([XYZ]\d{7}[A-Z])",         # NIE con etiqueta
        _ETIQ + r"([A-Z]{2}[A-Z0-9]{2,13})",  # VAT comunitario con etiqueta (ES + alfanum)
        r"\b([A-Z]\d{7}[A-Z0-9])\b",          # CIF sin etiqueta
        r"\b(\d{8}[A-Z])\b",                   # NIF persona fisica sin etiqueta
        r"\b([XYZ]\d{7}[A-Z])\b",              # NIE sin etiqueta
    ])


def _detectar_nombre_proveedor(text: str) -> str:
    skip = {"FACTURA", "INVOICE", "CIF", "NIF", "FECHA", "TOTAL", "BASE",
            "IVA", "ALBARAN", "PRESUPUESTO", "PEDIDO", "NOTA", "RECIBO", "ABONO"}
    for line in text.splitlines():
        clean = " ".join(line.split()).strip()
        if not clean or len(clean) < 3 or len(clean) > 70:
            continue
        upper = clean.upper()
        if any(tag in upper for tag in skip):
            continue
        # Descartar si parece una fecha
        if re.search(r"\d{1,2}[/\-]\d{1,2}[/\-]\d{2,4}", clean):
            continue
        # Descartar si solo hay numeros y simbolos
        if re.fullmatch(r"[\d\s\.,€$%\-/]+", clean):
            continue
        return clean
    return ""


def _detectar_numero_factura(text: str) -> str:
    return _search(text, [
        r"\b(?:Factura|Fra\.?|Invoice)\s*(?:N[ºo°]?\.?|No\.?|Num\.?|#)?\s*[:#\-]?\s*([A-Z0-9][A-Z0-9\/\.\-]{1,39})",
        r"\bN[ºo°]\s*(?:de\s+)?factura\s*[:#\-]?\s*([A-Z0-9][A-Z0-9\/\.\-]{1,39})",
        r"\b(?:Serie|REF\.?|Referencia)\s*[:#]?\s*([A-Z0-9][A-Z0-9\/\.\-]{1,39})",
    ])


def _detectar_fecha(text: str) -> str:
    # Primero buscar etiqueta explicita
    found = _search(text, [
        r"(?:Fecha\s+(?:de\s+)?(?:factura|emision|expedicion)|Invoice\s+date|Date)\s*[:#\-]?\s*"
        r"(\d{1,2}[\/\-\.]\d{1,2}[\/\-\.]\d{2,4}|\d{4}[\/\-\.]\d{1,2}[\/\-\.]\d{1,2})",
    ])
    if found:
        return found
    # Fallback: primera fecha en formato comun
    m = re.search(
        r"\b(\d{1,2}[\/\-]\d{1,2}[\/\-]\d{4}|\d{4}[\/\-]\d{2}[\/\-]\d{2})\b",
        text,
    )
    return m.group(1) if m else ""


def _detectar_total(text: str) -> float:
    return _buscar_importe(text, [
        r"\b(?:Total\s+(?:factura|importe|a\s+pagar)|Importe\s+total|TOTAL)\s*[:#\-]?\s*(?:EUR|€)?\s*([0-9][0-9\.,]*)",
        r"\b(?:Total\s+(?:factura|importe|a\s+pagar)|Importe\s+total|TOTAL)\s*[:#\-]?\s*([0-9][0-9\.,]*)\s*(?:EUR|€)?",
    ])


def _construir_descripcion(r: ParseResult) -> str:
    partes = ["Factura"]
    if r.proveedor_nombre:
        partes.append(r.proveedor_nombre)
    if r.numero_factura:
        partes.append(r.numero_factura)
    return " ".join(partes)


# ── Utilidades de parsing de texto/importes ───────────────────────────────────

def _search(text: str, patterns: list[str]) -> str:
    for pattern in patterns:
        m = re.search(pattern, text, flags=re.IGNORECASE)
        if m:
            return str(m.group(1)).strip()
    return ""


def _parse_amount(raw: str) -> float:
    """Convierte importes en formato espanol o ingles a float.

    Logica:
      - '1.234,56' -> 1234.56   (miles=punto, decimal=coma)
      - '1,234.56' -> 1234.56   (miles=coma, decimal=punto)
      - '1234,56'  -> 1234.56   (sin miles, decimal=coma)
      - '1234.56'  -> 1234.56   (sin miles, decimal=punto)
      - '1.234'    -> 1234.0    (solo miles, sin decimales)
    """
    s = str(raw or "").strip()
    if not s:
        return 0.0
    # Eliminar simbolo de moneda
    s = s.replace("€", "").replace("$", "").strip()
    if "," in s and "." in s:
        # El ultimo separador es el decimal
        if s.rfind(",") > s.rfind("."):
            s = s.replace(".", "").replace(",", ".")
        else:
            s = s.replace(",", "")
    elif "," in s:
        partes = s.split(",")
        # Coma decimal si la parte decimal tiene <= 2 digitos
        if len(partes) == 2 and len(partes[1]) <= 2:
            s = s.replace(",", ".")
        else:
            s = s.replace(",", "")
    # Punto como separador de miles sin coma: '1.234' -> '1234'
    elif "." in s:
        partes = s.split(".")
        if len(partes) > 1 and len(partes[-1]) == 3:
            s = s.replace(".", "")
    try:
        return round(float(s), 2)
    except Exception:
        return 0.0


def _buscar_importe(text: str, patterns: list[str]) -> float:
    raw = _search(text, patterns)
    return _parse_amount(raw)


def _sum_field(lineas: list[LineaFiscalParseada], campo: str) -> float:
    return round(sum(getattr(l, campo, 0.0) for l in lineas), 2)
