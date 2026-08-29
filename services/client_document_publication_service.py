"""Cola y publicacion fiable de facturas emitidas en el area del cliente."""

from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests

from services.backend_client_service import BackendClientService


LOG = logging.getLogger(__name__)


@dataclass(frozen=True)
class PublicationResult:
    factura_id: str
    status: str
    document_id: str = ""
    version: int = 0
    error: str = ""


class ClientDocumentPublicationService:
    """Persiste antes de enviar y recupera automaticamente los fallos."""

    def __init__(self, gestor, backend: BackendClientService | None = None):
        self.gestor = gestor
        self.backend = backend or BackendClientService()

    @staticmethod
    def _sha256(path: str) -> str:
        digest = hashlib.sha256()
        with open(path, "rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()

    def enqueue_and_publish(
        self, factura: dict, pdf_path: str, *, amount: float,
    ) -> PublicationResult:
        path = Path(pdf_path)
        if not path.is_file():
            raise FileNotFoundError(f"PDF no encontrado: {pdf_path}")
        factura_id = str(factura.get("id") or "").strip()
        if not factura_id:
            raise ValueError("La factura no tiene identificador")
        sha256 = self._sha256(str(path))
        queued = self.gestor.encolar_publicacion_area_cliente(
            factura_id, str(path), sha256, float(amount or 0),
        )
        if not queued:
            return PublicationResult(
                factura_id=factura_id,
                status="publicada",
                document_id=str(factura.get("area_cliente_documento_id") or ""),
                version=int(factura.get("area_cliente_version") or 0),
            )
        item = dict(factura)
        item.update({
            "area_cliente_pdf_path": str(path),
            "area_cliente_sha256": sha256,
            "area_cliente_importe": float(amount or 0),
            "area_cliente_intentos": 0,
        })
        return self._publish(item)

    def process_pending(self, limit: int = 20) -> list[PublicationResult]:
        results = []
        for item in self.gestor.listar_publicaciones_area_cliente_pendientes(limit):
            results.append(self._publish(item))
        return results

    def retry_invoice(self, factura: dict) -> PublicationResult:
        factura_id = str(factura.get("id") or "")
        self.gestor.reintentar_publicacion_area_cliente(factura_id)
        return self._publish(factura)

    def _publish(self, factura: dict) -> PublicationResult:
        factura_id = str(factura.get("id") or "")
        pdf_path = str(
            factura.get("area_cliente_pdf_path") or factura.get("pdf_path") or ""
        )
        try:
            if not self.backend.configured:
                raise RuntimeError(
                    "Falta configurar la URL del backend o el WorkstationToken"
                )
            if not Path(pdf_path).is_file():
                raise FileNotFoundError(f"PDF no encontrado: {pdf_path}")
            current_hash = self._sha256(pdf_path)
            queued_hash = str(factura.get("area_cliente_sha256") or "")
            if queued_hash and current_hash != queued_hash:
                amount = float(factura.get("area_cliente_importe") or 0)
                self.gestor.encolar_publicacion_area_cliente(
                    factura_id, pdf_path, current_hash, amount,
                )

            serie = str(factura.get("serie") or "").strip()
            numero = str(factura.get("numero") or "").strip()
            result = self.backend.publish_document(
                source_type="factura",
                source_id=factura_id,
                source_version=max(1, int(factura.get("area_cliente_version") or 1)),
                display_name=f"Factura {serie}{numero}".strip(),
                pdf_path=pdf_path,
                customer_tax_id=str(factura.get("nif") or "").strip(),
                fiscal_year=int(factura.get("ejercicio") or 0),
                amount=float(factura.get("area_cliente_importe") or 0),
                document_date=str(factura.get("fecha_expedicion") or ""),
                expected_sha256=current_hash,
            )
            document_id = str(result.get("id") or result.get("document_id") or "")
            version = int(result.get("source_version") or 1)
            self.gestor.marcar_publicacion_area_cliente_exitosa(
                factura_id, document_id, version,
            )
            return PublicationResult(
                factura_id=factura_id,
                status="publicada",
                document_id=document_id,
                version=version,
            )
        except Exception as exc:
            blocked = self._is_blocked(exc)
            attempts = int(factura.get("area_cliente_intentos") or 0) + 1
            next_retry = None
            if not blocked:
                delay = min(3600, 30 * (2 ** min(attempts - 1, 7)))
                next_retry = (
                    datetime.now(timezone.utc) + timedelta(seconds=delay)
                ).isoformat()
            message = self._error_message(exc)
            self.gestor.marcar_publicacion_area_cliente_fallida(
                factura_id,
                error=message,
                next_retry_at=next_retry,
                blocked=blocked,
            )
            LOG.warning(
                "Publicacion de factura %s %s: %s",
                factura_id, "bloqueada" if blocked else "pendiente", message,
            )
            return PublicationResult(
                factura_id=factura_id,
                status="bloqueada" if blocked else "error",
                error=message,
            )

    @staticmethod
    def _is_blocked(exc: Exception) -> bool:
        if isinstance(exc, (FileNotFoundError, ValueError)):
            return True
        if isinstance(exc, requests.HTTPError) and exc.response is not None:
            return exc.response.status_code in {400, 404, 409, 413, 415, 422}
        return False

    @staticmethod
    def _error_message(exc: Exception) -> str:
        if isinstance(exc, requests.HTTPError) and exc.response is not None:
            try:
                detail = exc.response.json().get("detail")
                if detail:
                    return str(detail)
            except Exception:
                pass
        return str(exc) or exc.__class__.__name__
