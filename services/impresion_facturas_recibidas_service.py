"""Impresion trazable de facturas recibidas desde su archivo definitivo."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class ResultadoImpresionFacturas:
    impresas: list[str] = field(default_factory=list)
    omitidas: list[str] = field(default_factory=list)
    errores: list[str] = field(default_factory=list)


class ImpresionFacturasRecibidasService:
    """Envia PDFs a Windows y registra solo los trabajos aceptados."""

    def __init__(self, gestor, *, imprimir_archivo=None):
        self._gestor = gestor
        self._imprimir_archivo = imprimir_archivo or self._imprimir_windows

    def imprimir(
        self, documento_ids: list[str], *, usuario: str = "",
    ) -> ResultadoImpresionFacturas:
        resultado = ResultadoImpresionFacturas()
        impresos: list[str] = []
        for documento_id in dict.fromkeys(documento_ids or []):
            documento = self._gestor.get_documento_archivo(str(documento_id))
            if not documento or documento.get("categoria_id") != "facturas_recibidas":
                resultado.omitidas.append(f"{documento_id}: no es una factura recibida")
                continue
            nombre = str(documento.get("nombre_original") or documento_id)
            path = Path(str(documento.get("ruta") or ""))
            if not path.is_file():
                resultado.errores.append(f"{nombre}: archivo no disponible")
                continue
            try:
                self._imprimir_archivo(path)
                impresos.append(str(documento_id))
                resultado.impresas.append(nombre)
            except Exception as exc:
                resultado.errores.append(f"{nombre}: {exc}")
        if impresos:
            self._gestor.registrar_impresion_documentos(impresos, usuario)
        return resultado

    @staticmethod
    def _imprimir_windows(path: Path) -> None:
        if os.name != "nt" or not hasattr(os, "startfile"):
            raise RuntimeError("La impresion multiple solo esta disponible en Windows.")
        os.startfile(str(path), "print")
