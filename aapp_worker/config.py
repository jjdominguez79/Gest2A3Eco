from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


def _required(name: str) -> str:
    value = str(os.environ.get(name) or "").strip()
    if not value:
        raise ValueError(f"Falta la variable obligatoria {name}")
    return value


def _secret(name: str) -> str:
    path = Path(_required(name))
    if not path.is_file():
        raise ValueError(f"No existe el secreto configurado en {name}: {path}")
    value = path.read_text(encoding="utf-8").strip()
    if not value:
        raise ValueError(f"El secreto {path} esta vacio")
    return value


@dataclass(frozen=True)
class AappWorkerConfig:
    backend_url: str
    api_key: str
    interval_seconds: int
    request_timeout_seconds: int
    headless: bool
    diagnostic_dir: Path | None

    @classmethod
    def from_environment(cls) -> "AappWorkerConfig":
        interval = max(10, int(os.environ.get("AAPP_INTERVAL_SECONDS", "30")))
        diagnostic = str(os.environ.get("AAPP_DIAGNOSTIC_DIR") or "").strip()
        return cls(
            backend_url=_required("AAPP_BACKEND_URL").rstrip("/"),
            api_key=_secret("AAPP_WORKER_API_KEY_FILE"),
            interval_seconds=interval,
            request_timeout_seconds=max(
                30, int(os.environ.get("AAPP_REQUEST_TIMEOUT_SECONDS", "120")),
            ),
            headless=str(os.environ.get("AAPP_HEADLESS", "true")).lower()
            in {"1", "true", "yes", "si"},
            diagnostic_dir=Path(diagnostic) if diagnostic else None,
        )
