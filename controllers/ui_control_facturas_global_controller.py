from __future__ import annotations

import json


class ControlFacturasGlobalController:
    """Consulta y normaliza el control global, sin logica de Tkinter."""

    def __init__(self, gestor, empresa_service):
        self._gestor = gestor
        self._empresa_service = empresa_service

    def cargar(self) -> tuple[list[dict], dict[str, str]]:
        empresas = self._empresa_service.listar_empresas_panel()
        nombres = {str(e["codigo"]): str(e.get("nombre") or e["codigo"]) for e in empresas}
        responsables = {
            str(e["codigo"]): str(e.get("responsable") or "").strip()
            for e in empresas
        }
        rows = self._gestor.listar_control_facturas_global(list(nombres))
        for row in rows:
            codigo = str(row.get("codigo_empresa") or "")
            row["empresa_nombre"] = nombres.get(codigo, codigo)
            row["responsable"] = responsables.get(codigo, "")
            row["generada"] = bool(row.get("generada"))
            row["total_calculado"] = self._total(row)
            row["estado_etiqueta"] = self._estado(row)
            row["modulo_destino"] = self._modulo_destino(row)
        return rows, nombres

    @staticmethod
    def _modulo_destino(row: dict) -> str:
        if row.get("tipo") == "emitida":
            return "facturacion"
        if not str(row.get("ocr_documento_id") or "").strip():
            return "gestion_documental"
        if str(row.get("estado_contable") or "").strip().lower() in {
            "pendiente_contabilizar", "exportada_a3", "contabilizada",
            "contabilizada_manual",
        }:
            return "contabilidad"
        return "ocr"

    @staticmethod
    def _estado(row: dict) -> str:
        if row.get("tipo") == "recibida":
            if row.get("estado_ocr") in {"error", "pendiente", "procesando"}:
                return "OCR " + str(row.get("estado_ocr"))
            if row.get("estado_validacion") == "pendiente":
                return "Pendiente revision"
            if row.get("estado_contable") == "pendiente_contabilizar":
                return "Pendiente contabilizar"
            if row.get("estado_contable") == "exportada_a3":
                return "Exportada a A3 · sin asiento"
            if row.get("estado_contable") == "contabilizada":
                return "Contabilizada"
            if row.get("estado_contable") == "contabilizada_manual":
                return "Contabilizada manualmente en A3"
        estado = str(row.get("estado_contable") or "").strip().lower()
        if estado == "pendiente":
            return "En contabilidad"
        if estado == "generado":
            return "Generado"
        return "Sin enviar a contabilidad"

    @staticmethod
    def _total(row: dict) -> float:
        if row.get("tipo") == "recibida":
            return float(row.get("total") or 0)
        try:
            lineas = json.loads(row.get("lineas_json") or "[]")
        except (TypeError, ValueError):
            lineas = []
        total = 0.0
        for linea in lineas:
            try:
                total += sum(float(str(linea.get(k) or 0).replace(",", ".")) for k in ("base", "cuota_iva", "cuota_re", "cuota_irpf"))
            except (AttributeError, TypeError, ValueError):
                continue
        return total
