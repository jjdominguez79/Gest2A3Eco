"""Cola durable para ejecutar OCR sin depender de una ventana Tkinter."""
from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

from services.ocr.ocr_service import OcrService


logger = logging.getLogger(__name__)


@dataclass
class ResultadoTrabajoOcr:
    trabajo_id: str
    estado: str
    documento_ocr_id: str = ""
    error: str = ""


class OcrBackgroundService:
    """Encola y consume OCR persistido en PostgreSQL.

    Los trabajos quedan disponibles para el siguiente arranque si el programa
    o el equipo se cierran durante el analisis.
    """

    def __init__(self, gestor):
        self._gestor = gestor

    def encolar(
        self, *, empresa_id: str, ejercicio: int, ruta_origen: str,
        tipo_documento: str = "factura_recibida", documento_archivo_id: str = "",
        usuario: str = "", max_intentos: int = 3,
    ) -> tuple[str, bool]:
        ruta = Path(str(ruta_origen or ""))
        if not ruta.is_file():
            raise ValueError(f"Archivo no disponible: {ruta}")
        if tipo_documento not in {"factura_recibida", "factura_emitida"}:
            raise ValueError("Tipo de documento OCR no admitido.")
        return self._gestor.encolar_trabajo_ocr({
            "empresa_id": str(empresa_id),
            "ejercicio": int(ejercicio),
            "ruta_origen": str(ruta),
            "tipo_documento": tipo_documento,
            "documento_archivo_id": str(documento_archivo_id or ""),
            "usuario": str(usuario or ""),
            "max_intentos": int(max_intentos),
        })

    def procesar_pendientes(self, limite: int = 1) -> list[ResultadoTrabajoOcr]:
        resultados = []
        for _ in range(max(0, int(limite))):
            trabajo = self._gestor.reclamar_trabajo_ocr()
            if not trabajo:
                break
            resultados.append(self._procesar(trabajo))
        return resultados

    def _procesar(self, trabajo: dict) -> ResultadoTrabajoOcr:
        trabajo_id = str(trabajo["id"])
        documento_ocr_id = str(trabajo.get("documento_ocr_id") or "")
        try:
            servicio = OcrService(
                self._gestor,
                str(trabajo["empresa_id"]),
                int(trabajo["ejercicio"]),
                usuario=str(trabajo.get("usuario") or ""),
                tipo_documento=str(
                    trabajo.get("tipo_documento") or "factura_recibida"
                ),
            )
            if documento_ocr_id:
                resultado = servicio.reprocesar_documento(documento_ocr_id)
            else:
                resultado = servicio.procesar_archivo(str(trabajo["ruta_origen"]))
                documento_ocr_id = str(resultado.get("documento_id") or "")

            archivo_id = str(trabajo.get("documento_archivo_id") or "")
            if archivo_id and documento_ocr_id:
                self._gestor.vincular_documento_archivo_ocr(
                    archivo_id, documento_ocr_id,
                )

            estado_ocr = str(resultado.get("estado") or "")
            if estado_ocr == "error":
                errores = resultado.get("errores") or ["El motor OCR no devolvio datos."]
                raise RuntimeError("; ".join(map(str, errores)))

            self._gestor.finalizar_trabajo_ocr(
                trabajo_id, resultado, documento_ocr_id,
            )
            return ResultadoTrabajoOcr(
                trabajo_id, "completado", documento_ocr_id,
            )
        except Exception as exc:
            estado = self._gestor.fallar_trabajo_ocr(
                trabajo_id, str(exc), documento_ocr_id=documento_ocr_id,
            )
            logger.warning(
                "[OCR segundo plano] Trabajo %s: %s (%s)",
                trabajo_id, exc, estado,
            )
            return ResultadoTrabajoOcr(
                trabajo_id, estado, documento_ocr_id, str(exc),
            )
