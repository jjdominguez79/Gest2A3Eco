"""Interfaz de envio a la AEAT y adaptador nulo.

``AeatSubmissionPort`` aisla el resto del sistema de los detalles de
transporte (SOAP, certificado, entorno de pruebas/produccion), ninguno de
los cuales esta implementado todavia (ver README.md). Mientras
``VERIFACTU_SUBMISSION_ENABLED`` sea false, ``NullAeatAdapter`` es el unico
adaptador activo: nunca abre una conexion de red y siempre devuelve un
resultado "incident" explicito, nunca "accepted".
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class AeatSubmissionResult:
    # accepted | rejected | incident
    status: str
    csv: str = ""
    error_code: str = ""
    error_detail: str = ""


class AeatSubmissionPort(Protocol):
    """Puerto de envio de un registro de facturacion ya construido."""

    def submit_alta(self, *, xml: str, huella: str) -> AeatSubmissionResult:
        ...

    def submit_anulacion(self, *, xml: str, huella: str) -> AeatSubmissionResult:
        ...


class NullAeatAdapter:
    """Adaptador inerte: no transmite nada. Uso mientras el flag este off.

    Devolver "incident" (no "rejected") es deliberado: no es que la AEAT
    haya rechazado el registro, es que todavia no se ha intentado enviar.
    fiscal_status debe reflejar esa distincion (ADR 0001, seccion 8/9).
    """

    def submit_alta(self, *, xml: str, huella: str) -> AeatSubmissionResult:
        return AeatSubmissionResult(
            status="incident",
            error_code="not_configured",
            error_detail=(
                "El envio real a la AEAT no esta implementado todavia "
                "(VERIFACTU_SUBMISSION_ENABLED=false)."
            ),
        )

    def submit_anulacion(self, *, xml: str, huella: str) -> AeatSubmissionResult:
        return AeatSubmissionResult(
            status="incident",
            error_code="not_configured",
            error_detail=(
                "El envio real a la AEAT no esta implementado todavia "
                "(VERIFACTU_SUBMISSION_ENABLED=false)."
            ),
        )
