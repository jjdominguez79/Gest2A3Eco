"""Bandeja operativa de facturas recibidas antes de su contabilizacion."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from services.import_a3_empresa import leer_numero_asiento_desde_a3
from services.ocr.background_service import OcrBackgroundService


@dataclass
class ResultadoLoteFacturas:
    completados: list[str] = field(default_factory=list)
    omitidos: list[str] = field(default_factory=list)
    errores: list[str] = field(default_factory=list)


class FacturasRecibidasPendientesService:
    def __init__(self, gestor, *, imprimir_archivo=None, buscar_asiento=None):
        self._gestor = gestor
        self._imprimir_archivo = imprimir_archivo or self._imprimir_windows
        self._buscar_asiento = buscar_asiento or leer_numero_asiento_desde_a3

    def listar(self) -> list[dict]:
        return self._gestor.listar_facturas_recibidas_pendientes_global()

    def imprimir(self, documento_ids: list[str], *, usuario: str = "") -> ResultadoLoteFacturas:
        resultado = ResultadoLoteFacturas()
        impresos = []
        for documento_id in dict.fromkeys(documento_ids or []):
            documento = self._factura(documento_id)
            if not documento:
                resultado.errores.append(f"{documento_id}: documento no encontrado")
                continue
            path = Path(str(documento.get("ruta") or ""))
            if not path.is_file():
                resultado.errores.append(
                    f"{documento.get('nombre_original') or documento_id}: archivo no disponible"
                )
                continue
            try:
                self._imprimir_archivo(path)
                impresos.append(str(documento_id))
                resultado.completados.append(
                    str(documento.get("nombre_original") or path.name)
                )
            except Exception as exc:
                resultado.errores.append(
                    f"{documento.get('nombre_original') or path.name}: {exc}"
                )
        if impresos:
            self._gestor.registrar_impresion_documentos(impresos, usuario)
        return resultado

    def enviar_a_ocr(
        self, documento_ids: list[str], *, usuario: str = "",
    ) -> ResultadoLoteFacturas:
        resultado = ResultadoLoteFacturas()
        cola = OcrBackgroundService(self._gestor)
        for documento_id in dict.fromkeys(documento_ids or []):
            documento = self._factura(documento_id)
            if not documento:
                resultado.errores.append(f"{documento_id}: documento no encontrado")
                continue
            nombre = str(documento.get("nombre_original") or documento_id)
            if documento.get("ocr_documento_id"):
                resultado.omitidos.append(nombre)
                continue
            try:
                _trabajo_id, creado = cola.encolar(
                    empresa_id=str(documento["codigo_empresa"]),
                    ejercicio=int(documento["ejercicio"]),
                    ruta_origen=str(documento["ruta"]),
                    documento_archivo_id=str(documento_id),
                    usuario=usuario,
                )
                if creado:
                    resultado.completados.append(nombre)
                else:
                    resultado.omitidos.append(f"{nombre}: ya estaba en cola")
            except Exception as exc:
                resultado.errores.append(f"{nombre}: {exc}")
        return resultado

    def marcar_contabilizadas(
        self, documento_ids: list[str], *, usuario: str = "",
        fecha_contable: str = "", numero_asiento: str = "",
        observaciones: str = "",
    ) -> int:
        return self._gestor.cambiar_estado_contable_documentos(
            documento_ids,
            "contabilizada_manual",
            usuario=usuario,
            fecha_contable=fecha_contable,
            numero_asiento=numero_asiento,
            observaciones=observaciones,
        )

    def devolver_a_pendientes(self, documento_ids: list[str]) -> int:
        return self._gestor.cambiar_estado_contable_documentos(
            documento_ids, "pendiente",
        )

    def capturar_asientos(
        self, documento_ids: list[str], *, usuario: str = "",
    ) -> ResultadoLoteFacturas:
        """Confirma el asiento real de A3 y conserva la via de contabilizacion."""
        resultado = ResultadoLoteFacturas()
        for documento_id in dict.fromkeys(documento_ids or []):
            try:
                documento = self._gestor.get_factura_recibida_archivo_para_captura(
                    str(documento_id),
                )
            except Exception as exc:
                resultado.errores.append(f"{documento_id}: {exc}")
                continue
            if not documento:
                resultado.errores.append(f"{documento_id}: documento no encontrado")
                continue
            nombre = str(documento.get("nombre_original") or documento_id)
            numero = str(documento.get("numero_factura_captura") or "").strip()[:10]
            if not numero:
                resultado.omitidos.append(f"{nombre}: faltan datos OCR de la factura")
                continue
            descripcion = str(
                documento.get("descripcion_captura") or f"Su Fra Nº. {numero}"
            ).strip()
            try:
                asiento = self._buscar_asiento(
                    self._codigo_a3(documento.get("codigo_empresa")),
                    int(documento.get("ejercicio") or 0),
                    numero,
                    descripcion,
                    mes=self._month_from_date(documento.get("fecha_captura")),
                )
                if not asiento:
                    resultado.omitidos.append(f"{numero}: no encontrada en A3ECO")
                    continue
                if self._exportada_por_suenlace(documento):
                    guardado = self._gestor.actualizar_asiento_documento_archivo(
                        str(documento_id), str(asiento),
                    )
                else:
                    guardado = self._gestor.cambiar_estado_contable_documentos(
                        [str(documento_id)],
                        "contabilizada_manual",
                        usuario=usuario,
                        # La busqueda confirma el asiento, pero no devuelve su fecha.
                        # No grabar como fecha contable la fecha OCR de la factura.
                        fecha_contable="",
                        numero_asiento=str(asiento),
                        observaciones="Asiento capturado automaticamente en A3ECO",
                    )
                if not guardado:
                    resultado.errores.append(f"{numero}: no se pudo guardar el asiento")
                    continue
                resultado.completados.append(f"{numero} -> asiento {asiento}")
            except Exception as exc:
                resultado.errores.append(f"{numero or nombre}: {exc}")
        return resultado

    @staticmethod
    def _exportada_por_suenlace(documento: dict) -> bool:
        estado = str(documento.get("estado_contable") or "").strip().lower()
        metodo = str(documento.get("metodo_contabilizacion") or "").strip().lower()
        return estado == "exportada_a3" or metodo == "ocr_suenlace"

    def _factura(self, documento_id: str) -> dict | None:
        documento = self._gestor.get_documento_archivo(str(documento_id))
        if not documento or documento.get("categoria_id") != "facturas_recibidas":
            return None
        return documento

    @staticmethod
    def _codigo_a3(codigo_empresa) -> str:
        digits = "".join(ch for ch in str(codigo_empresa or "") if ch.isdigit())
        return f"E{(digits.zfill(5) if digits else '00000')[:5]}"

    @staticmethod
    def _month_from_date(value) -> int | None:
        text = str(value or "").strip()
        for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y"):
            try:
                return datetime.strptime(text, fmt).month
            except ValueError:
                continue
        return None

    @staticmethod
    def _imprimir_windows(path: Path) -> None:
        if os.name != "nt" or not hasattr(os, "startfile"):
            raise RuntimeError("La impresion multiple solo esta disponible en Windows.")
        os.startfile(str(path), "print")
