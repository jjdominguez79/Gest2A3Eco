from __future__ import annotations

import logging
import signal
import threading

from sync_worker.config import MailSource, WorkerConfig
from sync_worker.graph import GraphApplicationMailClient
from sync_worker.repository import ComunicacionesRepository


LOG = logging.getLogger("gest2a3eco.mail_sync")


class MailSyncWorker:
    def __init__(self, config: WorkerConfig):
        self.config = config
        self.graph = GraphApplicationMailClient(
            tenant_id=config.tenant_id,
            client_id=config.client_id,
            certificate_path=config.certificate_path,
            certificate_password=config.certificate_password,
        )
        self.repository = ComunicacionesRepository(config.postgres_dsn)
        self.stop_event = threading.Event()

    @staticmethod
    def _matches_recipient(message: dict, recipient_filter: str) -> bool:
        expected = str(recipient_filter or "").strip().lower()
        if not expected:
            return True

        def address(item: dict) -> str:
            return str(
                ((item or {}).get("emailAddress") or {}).get("address") or ""
            ).strip().lower()

        recipients = [
            address(item)
            for key in ("toRecipients", "ccRecipients")
            for item in message.get(key) or []
        ]
        return expected in recipients

    def _run_source(self, source: MailSource) -> None:
        delta = self.repository.get_delta(source.sync_key)
        result = self.graph.sync_inbox(mailbox=source.mailbox, delta_link=delta)
        messages = result.messages
        if source.recipient_filter:
            messages = [
                message for message in messages
                if self._matches_recipient(message, source.recipient_filter)
            ]
        if not delta and not self.config.import_existing_on_first_run:
            LOG.info(
                "Primera ejecucion de %s: se establece el punto inicial sin importar "
                "%d mensajes existentes",
                source.mailbox, len(messages),
            )
            messages = []
        sync_kwargs = {"label": source.label} if source.label else {}
        inserted, duplicates = self.repository.sync_messages(
            source.mailbox, messages, result.delta_link, **sync_kwargs,
        )
        LOG.info(
            "Sincronizacion de %s completada: recibidos=%d nuevos=%d duplicados=%d",
            source.mailbox, len(messages), inserted, duplicates,
        )

    def run_once(self) -> None:
        sources = getattr(self.config, "mail_sources", None)
        if not sources:
            sources = (MailSource(mailbox=self.config.mailbox),)
        failures = []
        for source in sources:
            try:
                self._run_source(source)
            except Exception as exc:
                failures.append(exc)
                LOG.exception("Fallo de sincronizacion de %s: %s", source.mailbox, exc)
                self.repository.record_error(source.sync_key, str(exc))
        if failures and len(failures) == len(sources):
            raise failures[-1]

    def run_forever(self) -> None:
        while not self.stop_event.is_set():
            try:
                self.run_once()
            except Exception as exc:
                LOG.exception("Fallo de sincronizacion: %s", exc)
            self.stop_event.wait(self.config.interval_seconds)

    def stop(self, *_args) -> None:
        self.stop_event.set()


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    config = WorkerConfig.from_environment()
    worker = MailSyncWorker(config)
    signal.signal(signal.SIGTERM, worker.stop)
    signal.signal(signal.SIGINT, worker.stop)
    LOG.info(
        "Iniciando sincronizador para %s cada %d segundos",
        ", ".join(source.mailbox for source in config.mail_sources),
        config.interval_seconds,
    )
    worker.run_forever()
