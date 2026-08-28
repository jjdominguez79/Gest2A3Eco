"""Configuracion del worker Windows de facturacion.

Los secretos (token API, DSN PostgreSQL) se obtienen de Windows
Credential Manager via utils/credential_store.py. Solo los valores
no secretos se permiten en variables de entorno o fichero TOML.
"""

from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class WorkerConfig:
    # -- Conexion al backend --
    api_base_url: str
    worker_id: str
    # -- Lease y polling --
    lease_minutes: int
    poll_interval_seconds: int
    max_retries: int
    # -- Directorios --
    word_template_dir: str
    pdf_output_dir: str
    log_dir: str
    # -- Secretos (inyectados, no persistidos) --
    api_token: str
    desktop_dsn: str
    # -- Email logico (el envio real lo hace el backend) --
    sender_mailbox: str

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
            max_retries=int(os.getenv("INVOICE_WORKER_MAX_RETRIES", "5")),
            word_template_dir=os.getenv(
                "INVOICE_WORKER_TEMPLATE_DIR", "./plantillas_word",
            ),
            pdf_output_dir=os.getenv(
                "INVOICE_WORKER_PDF_DIR", "./pdfs_generados",
            ),
            log_dir=os.getenv(
                "INVOICE_WORKER_LOG_DIR", "./logs",
            ),
            api_token=os.getenv("INVOICE_WORKER_API_TOKEN", ""),
            desktop_dsn=os.getenv("INVOICE_WORKER_DESKTOP_DSN", ""),
            sender_mailbox=os.getenv(
                "INVOICE_WORKER_GRAPH_SENDER", "Oficina@gestinem.es",
            ),
        )

    @staticmethod
    def from_credential_store() -> WorkerConfig:
        """Carga config no secreta del entorno. Los secretos vienen SIEMPRE
        de Windows Credential Manager (Gest2A3Eco/WorkstationToken y
        Gest2A3Eco/PostgreSQL). Las variables INVOICE_WORKER_API_TOKEN y
        INVOICE_WORKER_DESKTOP_DSN solo se usan como fallback en desarrollo."""
        base = WorkerConfig.from_env()

        # Intentar Credential Manager primero (tiene prioridad en produccion)
        api_token = ""
        try:
            from utils.credential_store import get_workstation_token
            api_token = get_workstation_token() or ""
        except Exception:
            pass

        # Fallback a variable de entorno SOLO si no hay token en Credential Manager
        if not api_token:
            api_token = base.api_token  # puede ser "" si no esta definida

        desktop_dsn = ""
        try:
            from utils.credential_store import build_dsn_from_store
            host = os.getenv("INVOICE_WORKER_PG_HOST", "localhost")
            port = os.getenv("INVOICE_WORKER_PG_PORT", "5432")
            database = os.getenv("INVOICE_WORKER_PG_DB", "gest2a3eco")
            user_hint = os.getenv("INVOICE_WORKER_PG_USER", "")
            dsn = build_dsn_from_store(host, port, database, user_hint)
            desktop_dsn = dsn or ""
        except Exception:
            pass

        # Fallback a variable de entorno SOLO si no hay DSN en Credential Manager
        if not desktop_dsn:
            desktop_dsn = base.desktop_dsn  # puede ser "" si no esta definida

        return WorkerConfig(
            api_base_url=base.api_base_url,
            worker_id=base.worker_id,
            lease_minutes=base.lease_minutes,
            poll_interval_seconds=base.poll_interval_seconds,
            max_retries=base.max_retries,
            word_template_dir=base.word_template_dir,
            pdf_output_dir=base.pdf_output_dir,
            log_dir=base.log_dir,
            api_token=api_token,
            desktop_dsn=desktop_dsn,
            sender_mailbox=base.sender_mailbox,
        )
