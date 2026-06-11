"""
Contratos de datos del modulo OCR.

Todos los motores (PDF nativo, Tesseract, Azure, etc.) deben normalizar
su salida a OcrInvoiceResult.  El controlador y la vista solo consumen
este contrato; jamas dependen de la estructura interna de cada motor.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


# ── Estados del documento ────────────────────────────────────────────────────

class OcrDocumentState(str, Enum):
    PROCESANDO          = "procesando"
    ERROR               = "error"
    PENDIENTE_REVISION  = "pendiente_revision"
    PENDIENTE_CONTABILIZAR = "pendiente_contabilizar"
    CONTABILIZADA       = "contabilizada"
    DUPLICADO           = "duplicado"


# ── Tipos auxiliares ─────────────────────────────────────────────────────────

@dataclass
class OcrField:
    """Campo extraido por OCR con valor y nivel de confianza."""
    valor: Any = None
    confianza: float = 0.0
    fuente: str = ""          # "regex", "azure", "tesseract", etc.

    def __bool__(self) -> bool:
        return self.valor is not None and self.valor != "" and self.valor != 0.0


@dataclass
class OcrVatLine:
    """Una linea de IVA (tramo de base imponible)."""
    tipo_iva: float = 0.0
    base: float = 0.0
    cuota_iva: float = 0.0
    tipo_recargo: float = 0.0
    cuota_recargo: float = 0.0
    deducible: bool = True
    porcentaje_deduccion: float = 100.0
    cuenta_gasto: str = ""
    tipo_operacion_iva: str = "INTERIOR_DEDUCIBLE"

    @property
    def importe_deducible(self) -> float:
        return round(self.cuota_iva * self.porcentaje_deduccion / 100, 2)


@dataclass
class OcrRetentionLine:
    """Una linea de retencion IRPF."""
    base_retencion: float = 0.0
    tipo_retencion: float = 0.0
    importe_retencion: float = 0.0
    clase_retencion: str = "PROFESIONAL"  # PROFESIONAL | ARRENDAMIENTO | CAPITAL


# ── Resultado normalizado de OCR ─────────────────────────────────────────────

@dataclass
class OcrInvoiceResult:
    """
    Resultado normalizado de cualquier motor OCR para una factura recibida.

    Todos los campos son opcionales; errores contiene los campos faltantes
    o incoherencias detectadas.  El calificador 'confianza' (0-1) refleja
    la seguridad global del motor.
    """
    # Proveedor
    proveedor_nombre: str = ""
    proveedor_nif: str = ""

    # Numero y fechas
    numero_factura: str = ""
    fecha_factura: str = ""         # ISO YYYY-MM-DD o formato original
    fecha_vencimiento: str = ""

    # Importes globales (calculados desde lineas si estan disponibles)
    total: float = 0.0
    base_total: float = 0.0
    iva_total: float = 0.0
    retencion_total: float = 0.0

    # Lineas de detalle
    bases_iva: list[OcrVatLine] = field(default_factory=list)
    retenciones: list[OcrRetentionLine] = field(default_factory=list)

    # Texto y datos brutos
    texto: str = ""
    raw_json: dict = field(default_factory=dict)

    # Metadatos del proceso
    confianza: float = 0.0          # 0.0 - 1.0
    motor: str = ""                 # "pdf_text", "tesseract", "azure", etc.
    errores: list[str] = field(default_factory=list)

    # ── Propiedades calculadas ────────────────────────────────────────────────

    @property
    def es_valido(self) -> bool:
        """True si tiene los campos minimos para generar suenlace."""
        return bool(
            self.proveedor_nif
            and self.numero_factura
            and self.fecha_factura
            and self.total != 0.0
        )

    @property
    def estado_sugerido(self) -> OcrDocumentState:
        if not self.proveedor_nif or not self.numero_factura:
            return OcrDocumentState.ERROR
        return OcrDocumentState.PENDIENTE_REVISION

    @property
    def coherente(self) -> bool:
        """True si base + IVA - retencion aproxima al total."""
        if not self.total:
            return True
        esperado = round(self.base_total + self.iva_total - self.retencion_total, 2)
        return abs(esperado - self.total) <= 0.05

    def recalcular_totales_desde_lineas(self):
        """Recalcula base_total, iva_total y retencion_total desde las lineas."""
        self.base_total = round(sum(l.base for l in self.bases_iva), 2)
        self.iva_total  = round(sum(l.cuota_iva for l in self.bases_iva), 2)
        self.retencion_total = round(sum(r.importe_retencion for r in self.retenciones), 2)

    # ── Serializacion ─────────────────────────────────────────────────────────

    def to_dict(self) -> dict:
        return {
            "proveedor_nombre":  self.proveedor_nombre,
            "proveedor_nif":     self.proveedor_nif,
            "numero_factura":    self.numero_factura,
            "fecha_factura":     self.fecha_factura,
            "fecha_vencimiento": self.fecha_vencimiento,
            "total":             self.total,
            "base_total":        self.base_total,
            "iva_total":         self.iva_total,
            "retencion_total":   self.retencion_total,
            "bases_iva": [
                {
                    "tipo_iva":           l.tipo_iva,
                    "base":               l.base,
                    "cuota_iva":          l.cuota_iva,
                    "tipo_recargo":       l.tipo_recargo,
                    "cuota_recargo":      l.cuota_recargo,
                    "deducible":          l.deducible,
                    "porcentaje_deduccion": l.porcentaje_deduccion,
                    "cuenta_gasto":       l.cuenta_gasto,
                    "tipo_operacion_iva": l.tipo_operacion_iva,
                }
                for l in self.bases_iva
            ],
            "retenciones": [
                {
                    "base_retencion":    r.base_retencion,
                    "tipo_retencion":    r.tipo_retencion,
                    "importe_retencion": r.importe_retencion,
                    "clase_retencion":   r.clase_retencion,
                }
                for r in self.retenciones
            ],
            "texto":      self.texto,
            "raw_json":   self.raw_json,
            "confianza":  self.confianza,
            "motor":      self.motor,
            "errores":    self.errores,
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=2)

    @classmethod
    def from_dict(cls, d: dict) -> "OcrInvoiceResult":
        r = cls()
        for k in ("proveedor_nombre", "proveedor_nif", "numero_factura",
                   "fecha_factura", "fecha_vencimiento", "total", "base_total",
                   "iva_total", "retencion_total", "texto", "confianza", "motor"):
            if k in d:
                setattr(r, k, d[k])
        r.raw_json  = d.get("raw_json") or {}
        r.errores   = d.get("errores") or []
        r.bases_iva = [
            OcrVatLine(**{k: v for k, v in l.items() if k in OcrVatLine.__dataclass_fields__})
            for l in (d.get("bases_iva") or [])
        ]
        r.retenciones = [
            OcrRetentionLine(**{k: v for k, v in rr.items() if k in OcrRetentionLine.__dataclass_fields__})
            for rr in (d.get("retenciones") or [])
        ]
        return r
