"""Configuracion del worker Windows de facturacion."""

from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class WorkerConfig:
    api_base_url: str
    worker_id: str
    lease_minutes: int
    poll_interval_seconds: int
    word_template_dir: str
    pdf_output_dir: str
    # Token se obtiene de Windows Credential Manager en produccion
    api_token: str

    @staticmethod
    def from_env() -> WorkerConfig:
        return WorkerConfig(
            api_base_url=os.getenv(
                "INVOICE_WORKER_API_URL",
                "https://tramites.gestinem.es/api/v1/messaging/client/invoicing",
            ).rstrip("/"),
            worker_id=os.getenv("INVOICE_WORKER_ID", f"worker-{os.getpid()}"),
            lease_minutes=int(os.getenv("INVOICE_WORKER_LEASE_MINUTES", "10")),
            poll_interval_seconds=int(
                os.getenv("INVOICE_WORKER_POLL_SECONDS", "30"),
            ),
            word_template_dir=os.getenv(
                "INVOICE_WORKER_TEMPLATE_DIR", "./plantillas_word",
            ),
            pdf_output_dir=os.getenv(
                "INVOICE_WORKER_PDF_DIR", "./pdfs_generados",
            ),
            api_token=os.getenv("INVOICE_WORKER_API_TOKEN", ""),
        )
