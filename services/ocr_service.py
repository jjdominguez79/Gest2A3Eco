"""
Orquestador OCR.

Interfaz publica: OCRService.procesar_factura(file_path) -> dict
El dict devuelto mantiene el mismo contrato que usaba el controlador antes de Fase 4,
mas dos claves nuevas: 'bandeja' y 'error_mensaje' (usadas por el controlador desde Fase 2).

Motor de extraccion: intercambiable via services/ocr_provider.py
Parsing / validacion: delegado a services/ocr_parser_service.py
"""
from __future__ import annotations

from pathlib import Path

from utils.utilidades import load_app_config
from services.ocr_provider import build_provider_chain
from services.ocr_parser_service import OcrParserService


class OCRService:
    def __init__(self):
        self._cfg = load_app_config()
        self._providers = build_provider_chain(self._cfg)
        self._parser = OcrParserService()

    # ── Punto de entrada publico ──────────────────────────────────────────────

    def procesar_factura(self, file_path: str) -> dict:
        path = Path(file_path)
        if not path.exists():
            raise ValueError("El fichero indicado no existe.")

        source_type = _detect_source_type(path)
        ocr_result  = self._run_providers(path, source_type)

        if ocr_result.exito:
            parsed = self._parser.parsear_y_validar(ocr_result.texto)
        else:
            # Sin texto: error directo, el parser no puede hacer nada
            from services.ocr_parser_service import ParseResult
            parsed = ParseResult()
            parsed.errores_criticos = ocr_result.errores or ["Sin texto extraido del documento."]
            parsed.bandeja = "error"

        legacy = parsed.to_legacy_dict()
        legacy.update(
            {
                "backend":          ocr_result.proveedor,
                "source_type":      source_type,
                "texto_ocr":        ocr_result.texto,
                "confianza_ocr":    ocr_result.confianza,
                "avisos":           ocr_result.errores + parsed.avisos + parsed.errores_criticos,
                "pdf_path":         str(path) if source_type == "pdf" else "",
                "origen_path":      str(path),
                # Estado OCR: "procesado" si el motor extrajo texto, "error" si no
                "estado_ocr":       "procesado" if ocr_result.exito else "error",
                "estado_validacion": "pendiente",
                "estado_contable":  "",
                # bandeja y error_mensaje ya vienen de to_legacy_dict() pero los sobreescribimos
                # para que el proveedor OCR (sin texto) también los rellene correctamente
                "bandeja":          parsed.bandeja,
                "error_mensaje":    "; ".join(parsed.errores_criticos) if parsed.errores_criticos else "",
            }
        )
        return legacy

    # ── Cadena de proveedores ─────────────────────────────────────────────────

    def _run_providers(self, path: Path, source_type: str):
        from services.ocr_provider import OCRResult
        avisos: list[str] = []
        for provider in self._providers:
            if not provider.disponible():
                continue
            result = provider.extraer(path)
            avisos.extend(result.errores)
            if result.exito:
                result.errores = avisos
                return result
        # Ninguno extrajo texto
        if not avisos:
            if source_type == "pdf":
                avisos.append("El PDF no tiene texto embebido. Configura un motor OCR externo.")
            elif source_type == "image":
                avisos.append("La imagen requiere un motor OCR externo (Tesseract, Mindee, etc.).")
            else:
                avisos.append("Tipo de documento no soportado para OCR automatico.")
        return OCRResult(proveedor="none", errores=avisos)


# ── Utilidad de tipo de fuente ────────────────────────────────────────────────

def _detect_source_type(path: Path) -> str:
    ext = path.suffix.lower()
    if ext == ".pdf":
        return "pdf"
    if ext in {".png", ".jpg", ".jpeg", ".tif", ".tiff"}:
        return "image"
    return "other"
