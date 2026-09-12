from __future__ import annotations

import base64
import logging
import signal
import tempfile
import threading
from pathlib import Path

from aapp_worker.backend_client import AappBackendClient
from aapp_worker.config import AappWorkerConfig
from services.aapp.base import OpcionesSync
from services.aapp.base import obtener_conector
from services.aapp.cert_store import CertMaterial
from services.aapp.certificados import obtener_proveedor
from services.aapp import dehu_playwright  # noqa: F401


LOG = logging.getLogger("gest2a3eco.aapp_worker")


class AappWorker:
    def __init__(self, config: AappWorkerConfig, backend=None):
        self.config = config
        self.backend = backend or AappBackendClient(config)
        self.stop_event = threading.Event()

    def run_once(self) -> bool:
        item = self.backend.claim()
        if not item:
            return False
        try:
            self._process(item)
        except Exception as exc:
            LOG.exception("Fallo procesando la solicitud %s", item.get("id"))
            attempts = int(item.get("attempt_count") or 1)
            self.backend.fail(
                item,
                str(exc),
                retry_after_seconds=300 if attempts < 3 else None,
            )
        return True

    def _process(self, item: dict) -> None:
        if item["certificate_type"] == "DEHU_SYNC":
            self._process_dehu(item)
            return
        provider = obtener_proveedor(item["certificate_type"])
        if provider is None:
            self.backend.fail(
                item,
                "El tipo de certificado no tiene conector disponible",
                code="unsupported_type",
            )
            return
        material = self.backend.certificate_material(item)
        with tempfile.TemporaryDirectory(prefix="gestinem-aapp-") as directory:
            workdir = Path(directory)
            pfx_path = workdir / "cliente.pfx"
            pdf_path = workdir / f"{item['certificate_type'].lower()}.pdf"
            pfx_path.write_bytes(base64.b64decode(material["pfx_base64"]))
            cert = CertMaterial(
                cert_id="central",
                nombre=material.get("file_name") or "certificado",
                nif_titular=None,
                ruta_archivo=str(pfx_path),
                password=material.get("password") or "",
                fecha_caducidad=material.get("valid_until"),
            )
            options = OpcionesSync(
                headless=self.config.headless,
                descargar_pdf=True,
                carpeta_descargas=str(workdir),
                ruta_pdf_destino=str(pdf_path),
                modo_diagnostico=self.config.diagnostic_dir is not None,
                carpeta_diagnostico=(
                    str(self.config.diagnostic_dir)
                    if self.config.diagnostic_dir is not None else None
                ),
                parametros=dict(item.get("parameters") or {}),
                log=lambda message: LOG.info("%s: %s", item["id"], message),
            )
            result = provider.obtener(cert, item["certificate_type"], options)
            if result.estado == "PENDIENTE":
                self.backend.fail(
                    item,
                    result.mensaje or "El tramite requiere intervencion",
                    code="needs_action",
                    needs_action=True,
                )
                return
            if not result.ok or result.estado != "OBTENIDO" or not result.pdf_path:
                raise RuntimeError(result.mensaje or "El organismo no devolvio el certificado")
            final_pdf = Path(result.pdf_path)
            if not final_pdf.is_file() or not final_pdf.read_bytes().startswith(b"%PDF-"):
                raise RuntimeError("El organismo no devolvio un PDF valido")
            document = self.backend.publish_pdf(item, final_pdf)
            document_id = str(document.get("id") or document.get("document_id") or "")
            if not document_id:
                raise RuntimeError("El backend no devolvio el identificador del documento")
            self.backend.complete(item, document_id, result.resultado or "")
            LOG.info("Solicitud %s completada", item["id"])

    def _process_dehu(self, item: dict) -> None:
        connector = obtener_conector("DEHU")
        if connector is None:
            raise RuntimeError("El conector DEHu no esta disponible en el worker")
        material = self.backend.certificate_material(item)
        parameters = item.get("parameters") or {}
        with tempfile.TemporaryDirectory(prefix="gestinem-dehu-") as directory:
            workdir = Path(directory)
            pfx_path = workdir / "cliente.pfx"
            pfx_path.write_bytes(base64.b64decode(material["pfx_base64"]))
            cert = CertMaterial(
                cert_id="central",
                nombre=material.get("file_name") or "certificado",
                nif_titular=parameters.get("tax_id"),
                ruta_archivo=str(pfx_path),
                password=material.get("password") or "",
                fecha_caducidad=material.get("valid_until"),
            )
            options = OpcionesSync(
                headless=self.config.headless,
                descargar_pdf=True,
                carpeta_descargas=str(workdir),
                nif_filtro=parameters.get("tax_id") or None,
                modo_diagnostico=self.config.diagnostic_dir is not None,
                carpeta_diagnostico=(
                    str(self.config.diagnostic_dir)
                    if self.config.diagnostic_dir is not None else None
                ),
                log=lambda message: LOG.info("%s: %s", item["id"], message),
            )
            result = connector.sincronizar(
                {
                    "id": parameters.get("mailbox_id") or "dehu-central",
                    "nombre": parameters.get("mailbox_name") or "DEHu",
                    "organismo_codigo": "DEHU",
                    "codigo_empresa": parameters.get("company_code") or "",
                    "modo_descarga": parameters.get("download_mode") or "PENDIENTES",
                },
                cert,
                options,
            )
            if not result.ok:
                raise RuntimeError(result.mensaje or "No se pudo sincronizar DEHu")
            document_ids = []
            for notification in result.notificaciones:
                if not notification.pdf_path:
                    continue
                pdf_path = Path(notification.pdf_path)
                if not pdf_path.is_file() or not pdf_path.read_bytes().startswith(b"%PDF-"):
                    continue
                document = self.backend.publish_notification_pdf(
                    item, notification, pdf_path,
                )
                document_id = str(document.get("id") or document.get("document_id") or "")
                if document_id:
                    document_ids.append(document_id)
            summary = (
                f"{result.total} notificacion(es) detectada(s); "
                f"{len(document_ids)} documento(s) publicado(s)."
            )
            self.backend.complete(
                item,
                document_ids[0] if document_ids else None,
                summary,
            )
            LOG.info("Sincronizacion DEHu %s completada: %s", item["id"], summary)

    def run_forever(self) -> None:
        while not self.stop_event.is_set():
            processed = self.run_once()
            if not processed:
                self.stop_event.wait(self.config.interval_seconds)

    def stop(self, *_args) -> None:
        self.stop_event.set()


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    worker = AappWorker(AappWorkerConfig.from_environment())
    signal.signal(signal.SIGTERM, worker.stop)
    signal.signal(signal.SIGINT, worker.stop)
    LOG.info("Iniciando worker AAPP")
    worker.run_forever()
