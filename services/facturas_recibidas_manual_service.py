"""Circuito manual de facturas recibidas archivadas, independiente del OCR."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from services.import_a3_empresa import leer_numero_asiento_desde_a3


@dataclass
class ResultadoCapturaManual:
    numero_factura: str
    numero_asiento: str = ""
    encontrado: bool = False


class FacturasRecibidasManualService:
    def __init__(self, gestor, *, buscar_asiento=None):
        self._gestor = gestor
        self._buscar_asiento = buscar_asiento or leer_numero_asiento_desde_a3

    def datos_captura(self, documento_id: str) -> dict | None:
        return self._gestor.get_factura_recibida_archivo_para_captura(
            str(documento_id),
        )

    def capturar_asiento(
        self,
        documento_id: str,
        *,
        numero_factura: str,
        fecha_factura: str = "",
        descripcion: str = "",
        usuario: str = "",
    ) -> ResultadoCapturaManual:
        documento = self.datos_captura(documento_id)
        if not documento:
            raise ValueError("No se encontro la factura recibida archivada.")
        numero = str(numero_factura or "").strip()
        if not numero:
            raise ValueError("Indica el numero de factura para buscarla en A3ECO.")
        concepto = str(descripcion or f"Su Fra Nº. {numero}").strip()
        asiento = self._buscar_asiento(
            self._codigo_a3(documento.get("codigo_empresa")),
            int(documento.get("ejercicio") or 0),
            numero[:10],
            concepto,
            mes=self._month_from_date(fecha_factura),
        )
        resultado = ResultadoCapturaManual(numero_factura=numero)
        if not asiento:
            return resultado

        estado = str(documento.get("estado_contable") or "").strip().lower()
        metodo = str(documento.get("metodo_contabilizacion") or "").strip().lower()
        if estado == "exportada_a3" or metodo == "ocr_suenlace":
            guardado = self._gestor.actualizar_asiento_documento_archivo(
                str(documento_id), str(asiento),
            )
        else:
            guardado = self._gestor.cambiar_estado_contable_documentos(
                [str(documento_id)],
                "contabilizada_manual",
                usuario=usuario,
                # La fecha se usa solo para elegir el fichero mensual de A3;
                # la lectura no devuelve la fecha contable real del asiento.
                fecha_contable="",
                numero_asiento=str(asiento),
                observaciones="Asiento capturado automaticamente en A3ECO",
            )
        if guardado:
            resultado.numero_asiento = str(asiento)
            resultado.encontrado = True
        return resultado

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
