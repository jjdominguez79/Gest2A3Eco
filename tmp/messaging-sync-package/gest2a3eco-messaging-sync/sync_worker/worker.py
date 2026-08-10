from __future__ import annotations

import logging
import signal
import threading

from sync_worker.config import WorkerConfig
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

    def run_once(self) -> None:
        delta = self.repository.get_delta(self.config.mailbox)
        result = self.graph.sync_inbox(mailbox=self.config.mailbox, delta_link=delta)
        messages = result.messages
        if not delta and not self.config.import_existing_on_first_run:
            LOG.info(
                "Primera ejecucion: se establece el punto inicial sin importar %d mensajes existentes",
                len(messages),
            )
            messages = []
        inserted, duplicates = self.repository.sync_messages(
            self.config.mailbox, messages, result.delta_link
        )
        LOG.info(
            "Sincronizacion completada: recibidos=%d nuevos=%d duplicados=%d",
            len(messages), inserted, duplicates,
        )

    def run_forever(self) -> None:
        while not self.stop_event.is_set():
            try:
                self.run_once()
            except Exception as exc:
                LOG.exception("Fallo de sincronizacion: %s", exc)
                self.repository.record_error(self.config.mailbox, str(exc))
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
        config.mailbox, config.interval_seconds,
    )
    worker.run_forever()
