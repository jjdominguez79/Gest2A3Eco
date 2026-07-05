from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from services.facturae.facturae_builder import build_facturae_document, build_facturae_xml
from services.facturae.facturae_codes import (
    FACTURAE_STATUS_GENERADO,
    FACTURAE_STATUS_NO_GENERADO,
    INVOICE_CLASS_CORRECTIVE,
    INVOICE_CLASS_ORIGINAL,
)
from utils.utilidades import aplicar_descuento_total_lineas
from services.facturae.facturae_validator import (
    build_facturae_error_payload,
    validate_facturae_payload,
    validate_facturae_xml_content,
)


@dataclass(slots=True)
class FacturaeExportResult:
    ok: bool
    errors: list[str]
    xml_content: str = ""
    output_path: str = ""
    warning: str = ""
    facturae_status: str = FACTURAE_STATUS_NO_GENERADO


class FacturaeExporter:
    unsigned_warning = (
        "Fichero Facturae generado sin firma electronica. Puede validarse estructuralmente, "
        "pero para presentacion en FACe normalmente debe firmarse con certificado digital."
    )

    def build_payload(self, factura: dict, emisor: dict, receptor: dict, relacion_tercero: dict | None = None) -> dict:
        relacion_tercero = relacion_tercero or {}
        lineas = [
            ln for ln in aplicar_descuento_total_lineas(
                list(factura.get("lineas") or []),
                factura.get("descuento_total_tipo"),
                factura.get("descuento_total_valor"),
            )
            if str(ln.get("tipo") or "").strip().lower() != "obs"
        ]
        is_corrective = any(float(str((ln.get("base") or 0)).replace(",", ".")) < 0 for ln in lineas)
        corrective = None
        if is_corrective:
            corrective = {
                "invoice_number": str(factura.get("numero_rectificada") or factura.get("numero_original_rectificada") or "").strip(),
                "invoice_series_code": str(factura.get("serie_rectificada") or "").strip(),
                "reason_code": str(factura.get("facturae_reason_code") or "01").strip(),
                "reason_description": str(factura.get("facturae_reason_description") or "Factura rectificativa").strip(),
            }
            if not corrective["invoice_number"]:
                corrective = None

        return {
            "factura": factura,
            "emisor": emisor,
            "receptor": receptor,
            "relacion_tercero": relacion_tercero,
            "lineas": lineas,
            "totales": self._totales(factura, lineas),
            "invoice_class": INVOICE_CLASS_CORRECTIVE if is_corrective else INVOICE_CLASS_ORIGINAL,
            "corrective": corrective,
        }

    def validate(self, factura: dict, emisor: dict, receptor: dict, relacion_tercero: dict | None = None) -> list[str]:
        payload = self.build_payload(factura, emisor, receptor, relacion_tercero)
        return validate_facturae_payload(payload)

    def export(self, factura: dict, emisor: dict, receptor: dict, output_path: str, relacion_tercero: dict | None = None) -> FacturaeExportResult:
        payload = self.build_payload(factura, emisor, receptor, relacion_tercero)
        errors = validate_facturae_payload(payload)
        if errors:
            return FacturaeExportResult(ok=False, errors=errors, facturae_status=build_facturae_error_payload(errors)["facturae_status"])

        document = build_facturae_document(payload)
        xml_content = build_facturae_xml(document)
        xml_errors = validate_facturae_xml_content(xml_content)
        if xml_errors:
            return FacturaeExportResult(ok=False, errors=xml_errors, facturae_status=build_facturae_error_payload(xml_errors)["facturae_status"])

        target = Path(output_path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(xml_content, encoding="utf-8")
        return FacturaeExportResult(
            ok=True,
            errors=[],
            xml_content=xml_content,
            output_path=str(target),
            warning=self.unsigned_warning,
            facturae_status=FACTURAE_STATUS_GENERADO,
        )

    def build_factura_persistence_update(self, factura: dict, result: FacturaeExportResult) -> dict:
        updated = dict(factura)
        updated["facturae_status"] = result.facturae_status
        updated["facturae_error"] = "\n".join(result.errors) if result.errors else ""
        if result.ok:
            updated["facturae_xml_path"] = result.output_path
            updated["facturae_generated_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        else:
            updated.update(build_facturae_error_payload(result.errors))
        return updated

    def _totales(self, factura: dict, lineas: list[dict]) -> dict:
        base = sum(float(str((ln.get("base") or 0)).replace(",", ".")) for ln in lineas)
        iva = sum(float(str((ln.get("cuota_iva") or 0)).replace(",", ".")) for ln in lineas)
        ret = sum(float(str((ln.get("cuota_irpf") or 0)).replace(",", ".")) for ln in lineas)
        total = float(str(factura.get("retencion_importe") or 0).replace(",", ".")) if factura.get("retencion_aplica") else ret
        return {
            "base": round(base, 2),
            "iva": round(iva, 2),
            "ret": round(abs(total), 2),
            "total": round(base + iva - abs(total), 2),
        }


def sign_facturae_xml(xml_path: str, certificate_path: str, certificate_password: str) -> str:
    raise NotImplementedError(
        "La firma XAdES-EPES no esta implementada en esta fase. Punto de extension reservado."
    )
