"""Impresion trazable de facturas recibidas desde su archivo definitivo."""
from __future__ import annotations

import os
import tempfile
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class ResultadoImpresionFacturas:
    impresas: list[str] = field(default_factory=list)
    omitidas: list[str] = field(default_factory=list)
    errores: list[str] = field(default_factory=list)


class ImpresionFacturasRecibidasService:
    """Envia PDFs a Windows y registra solo los trabajos aceptados."""

    def __init__(
        self, gestor, *, imprimir_archivo=None,
        directorio_temporal: str | Path | None = None,
    ):
        self._gestor = gestor
        self._imprimir_archivo = imprimir_archivo or self._imprimir_windows
        self._directorio_temporal = Path(
            directorio_temporal
            or Path(tempfile.gettempdir()) / "Gest2A3Eco" / "impresion"
        )

    def imprimir(
        self, documento_ids: list[str], *, usuario: str = "",
        paginas_por_documento: dict[str, list[int]] | None = None,
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
                ruta_impresion = path
                if paginas_por_documento is not None:
                    paginas = paginas_por_documento.get(str(documento_id), [])
                    if not paginas:
                        resultado.omitidas.append(f"{nombre}: sin paginas seleccionadas")
                        continue
                    ruta_impresion = self._crear_pdf_paginas(path, paginas)
                self._imprimir_archivo(ruta_impresion)
                impresos.append(str(documento_id))
                resultado.impresas.append(nombre)
            except Exception as exc:
                resultado.errores.append(f"{nombre}: {exc}")
        if impresos:
            self._gestor.registrar_impresion_documentos(impresos, usuario)
        return resultado

    def _crear_pdf_paginas(self, path: Path, paginas: list[int]) -> Path:
        if path.suffix.lower() != ".pdf":
            raise ValueError("la seleccion de paginas solo esta disponible para PDF")
        try:
            import fitz
        except ImportError as exc:
            raise RuntimeError(
                "PyMuPDF no esta disponible para preparar las paginas seleccionadas."
            ) from exc

        paginas_unicas = sorted({int(pagina) for pagina in paginas})
        with fitz.open(str(path)) as origen:
            total = len(origen)
            if not paginas_unicas or paginas_unicas[0] < 1 or paginas_unicas[-1] > total:
                raise ValueError("la seleccion contiene paginas no validas")
            if paginas_unicas == list(range(1, total + 1)):
                return path
            self._limpiar_temporales_antiguos()
            self._directorio_temporal.mkdir(parents=True, exist_ok=True)
            destino = self._directorio_temporal / (
                f"{path.stem}-{uuid.uuid4().hex[:10]}-paginas.pdf"
            )
            salida = fitz.open()
            try:
                for pagina in paginas_unicas:
                    salida.insert_pdf(
                        origen, from_page=pagina - 1, to_page=pagina - 1,
                    )
                salida.save(str(destino), garbage=4, deflate=True)
            finally:
                salida.close()
        return destino

    def _limpiar_temporales_antiguos(self) -> None:
        if not self._directorio_temporal.is_dir():
            return
        limite = time.time() - (7 * 24 * 60 * 60)
        for path in self._directorio_temporal.glob("*-paginas.pdf"):
            try:
                if path.stat().st_mtime < limite:
                    path.unlink()
            except OSError:
                continue

    @staticmethod
    def _imprimir_windows(path: Path) -> None:
        if os.name != "nt" or not hasattr(os, "startfile"):
            raise RuntimeError("La impresion multiple solo esta disponible en Windows.")
        os.startfile(str(path), "print")
