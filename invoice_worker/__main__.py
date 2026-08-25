"""Punto de entrada del worker de facturacion online."""

import logging

from invoice_worker.config import WorkerConfig
from invoice_worker.worker import InvoiceWorker


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    )
    config = WorkerConfig.from_env()
    if not config.api_token:
        raise SystemExit(
            "INVOICE_WORKER_API_TOKEN no configurado. "
            "Usa Windows Credential Manager en produccion."
        )

    worker = InvoiceWorker(config)
    worker.run_forever()


if __name__ == "__main__":
    main()
