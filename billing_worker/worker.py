"""Bucle principal de billing_worker.

Reclama trabajo de ``ClientInvoiceProcessingQueue`` via
``POST /worker/claim`` (lease con SELECT FOR UPDATE SKIP LOCKED en el
backend), renderiza el PDF, lo sube, publica el documento y dispara email y
FCM (ambos idempotentes y resueltos server-side). Puede ejecutarse con
varias replicas sin duplicar trabajo porque el backend es quien otorga el
lease, no el worker.

Apagado ordenado: SIGTERM/SIGINT marcan ``stop_event``; el trabajo en curso
(``_process``) siempre termina su secuencia de llamadas HTTP (cada una
confirma o libera su propio estado en el backend) antes de que el bucle
vuelva a comprobar la senal, por lo que nunca se corta a mitad de una
subida de PDF sin que la cola quede en un estado recuperable (lease
caducado -> SKIP LOCKED la reclama de nuevo, o ``error`` -> reintento).
"""

from __future__ import annotations

import logging
import signal
import time

import threading

from billing_worker.backend_client import BillingBackendClient
from billing_worker.config import BillingWorkerConfig
from billing_worker.handlers.render_pdf import render_invoice_pdf, sha256_hex

LOG = logging.getLogger("gest2a3eco.billing_worker")


class BillingWorker:
    def __init__(
        self,
        config: BillingWorkerConfig,
        backend: BillingBackendClient | None = None,
    ) -> None:
        self.config = config
        self.backend = backend or BillingBackendClient(config)
        self.stop_event = threading.Event()
        self.jobs_processed_total = 0
        self.jobs_failed_total = 0
        self._last_heartbeat_at = 0.0

    def run_once(self) -> bool:
        """Reclama y procesa un unico trabajo. Devuelve True si habia trabajo.

        Puede lanzar si ``claim()`` falla (backend inalcanzable); ese caso lo
        gestiona ``run_forever`` con backoff. Un fallo procesando un trabajo
        ya reclamado se captura aqui y se reporta al backend: nunca se deja
        sin informar un lease que ya se tiene.
        """
        claimed = self.backend.claim()
        if not claimed:
            return False

        invoice_id = str(claimed["invoice_id"])
        try:
            self._process(invoice_id)
            self.jobs_processed_total += 1
        except Exception as exc:  # noqa: BLE001 - se reporta explicitamente
            self.jobs_failed_total += 1
            LOG.exception("[invoice=%s] fallo procesando el trabajo", invoice_id)
            try:
                self.backend.report_error(invoice_id, str(exc))
            except Exception:
                LOG.exception(
                    "[invoice=%s] no se pudo reportar el error; el lease "
                    "caducara y se reclamara de nuevo", invoice_id,
                )
        return True

    def _process(self, invoice_id: str) -> None:
        """Ejecuta render_pdf -> publish_document -> send_email -> send_notification.

        Cada paso comprueba el estado actual antes de repetir trabajo
        (idempotencia por tipo de trabajo, seccion 10 del encargo): si el
        worker se reinicia a mitad de la secuencia, el siguiente intento
        reanuda en el paso que falte, no desde el principio.
        """
        status = self.backend.get_status(invoice_id)

        if not status.get("pdf_uploaded"):
            payload = self.backend.get_payload(invoice_id)
            content = render_invoice_pdf(payload)
            self.backend.upload_pdf(invoice_id, content, sha256_hex(content))
            status = self.backend.get_status(invoice_id)

        if not status.get("document_published"):
            self.backend.publish_document(invoice_id)

        self.backend.send_email(invoice_id)

        # send_notification (FCM) es best-effort: nunca debe tumbar un
        # trabajo cuya parte fiscal/PDF/email ya se completo correctamente.
        try:
            self.backend.send_fcm(invoice_id)
        except Exception:
            LOG.warning(
                "[invoice=%s] no se pudo enviar la notificacion push", invoice_id,
                exc_info=True,
            )

    def maybe_heartbeat(self, *, force: bool = False) -> None:
        now = time.monotonic()
        if not force and (now - self._last_heartbeat_at) < self.config.heartbeat_interval_seconds:
            return
        try:
            self.backend.heartbeat(
                jobs_processed_total=self.jobs_processed_total,
                jobs_failed_total=self.jobs_failed_total,
            )
        except Exception:
            LOG.warning("No se pudo enviar el heartbeat al backend", exc_info=True)
        self._last_heartbeat_at = now

    def run_forever(self) -> None:
        consecutive_errors = 0
        self.maybe_heartbeat(force=True)
        while not self.stop_event.is_set():
            try:
                processed = self.run_once()
            except Exception:
                consecutive_errors += 1
                backoff = min(
                    self.config.poll_interval_seconds * (2 ** consecutive_errors),
                    self.config.max_backoff_seconds,
                )
                LOG.exception(
                    "No se pudo consultar la cola del backend; se "
                    "reintentara en %s segundos", backoff,
                )
                self.maybe_heartbeat()
                self.stop_event.wait(backoff)
                continue

            consecutive_errors = 0
            self.maybe_heartbeat()
            if not processed:
                self.stop_event.wait(self.config.poll_interval_seconds)

    def stop(self, *_args) -> None:
        LOG.info(
            "Senal de apagado recibida: se terminara el trabajo en curso y "
            "se detendra el bucle"
        )
        self.stop_event.set()


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    config = BillingWorkerConfig.from_environment()
    worker = BillingWorker(config)
    signal.signal(signal.SIGTERM, worker.stop)
    signal.signal(signal.SIGINT, worker.stop)
    LOG.info("Iniciando billing_worker (instance_id=%s)", config.instance_id)
    worker.run_forever()
