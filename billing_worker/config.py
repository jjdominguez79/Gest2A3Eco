from __future__ import annotations

import os
import socket
import uuid
from dataclasses import dataclass
from pathlib import Path


def _required(name: str) -> str:
    value = str(os.environ.get(name) or "").strip()
    if not value:
        raise ValueError(f"Falta la variable obligatoria {name}")
    return value


def _secret(name: str) -> str:
    """Lee un secreto desde un archivo (Docker/Railway secret), nunca inline.

    Mismo patron que aapp_worker/config.py y sync_worker/config.py.
    """
    path = Path(_required(name))
    if not path.is_file():
        raise ValueError(f"No existe el secreto configurado en {name}: {path}")
    value = path.read_text(encoding="utf-8").strip()
    if not value:
        raise ValueError(f"El secreto {path} esta vacio")
    return value


@dataclass(frozen=True)
class BillingWorkerConfig:
    backend_url: str
    api_key: str
    instance_id: str
    poll_interval_seconds: int
    lease_minutes: int
    request_timeout_seconds: int
    heartbeat_interval_seconds: int
    max_backoff_seconds: int

    @classmethod
    def from_environment(cls) -> "BillingWorkerConfig":
        instance_id = str(
            os.environ.get("BILLING_WORKER_ID")
            or f"{socket.gethostname()}-{uuid.uuid4().hex[:8]}"
        )[:120]
        return cls(
            backend_url=_required("BILLING_WORKER_BACKEND_URL").rstrip("/"),
            api_key=_secret("BILLING_WORKER_API_KEY_FILE"),
            instance_id=instance_id,
            poll_interval_seconds=max(
                5, int(os.environ.get("BILLING_WORKER_POLL_INTERVAL_SECONDS", "15")),
            ),
            lease_minutes=max(
                1, min(int(os.environ.get("BILLING_WORKER_LEASE_MINUTES", "10")), 60),
            ),
            request_timeout_seconds=max(
                10, int(os.environ.get("BILLING_WORKER_REQUEST_TIMEOUT_SECONDS", "60")),
            ),
            heartbeat_interval_seconds=max(
                30, int(os.environ.get("BILLING_WORKER_HEARTBEAT_INTERVAL_SECONDS", "60")),
            ),
            max_backoff_seconds=max(
                60, int(os.environ.get("BILLING_WORKER_MAX_BACKOFF_SECONDS", "300")),
            ),
        )
