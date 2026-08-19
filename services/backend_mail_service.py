from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path

import requests

from utils.utilidades import load_app_config


@dataclass
class BackendMailResult:
    sender: str = ""
    message_id: str = ""
    internet_message_id: str = ""


class BackendMailService:
    """Envia correo mediante el backend; el escritorio nunca recibe secretos Graph."""

    def __init__(self, config: dict | None = None, session=None):
        cfg = config or load_app_config()
        self.base_url = str(
            cfg.get("integrations_api_url") or cfg.get("dgt_api_url") or ""
        ).rstrip("/")
        from utils.credential_store import get_workstation_token
        self.token = get_workstation_token() or os.getenv("GEST2A3ECO_WORKSTATION_TOKEN", "")
        self.http = session or requests.Session()

    @property
    def configured(self) -> bool:
        return bool(self.base_url and self.token)

    def send(
        self, *, to: list[str], cc: list[str] | None = None,
        bcc: list[str] | None = None, subject: str, body: str,
        attachments: list[str] | None = None,
        inline_attachments: list[dict] | None = None,
    ) -> BackendMailResult:
        if not self.configured:
            raise ValueError(
                "El backend no esta disponible: revisa la URL de integraciones y "
                "el token de este puesto."
            )
        opened = []
        try:
            files = []
            for raw in attachments or []:
                path = Path(raw)
                handle = path.open("rb")
                opened.append(handle)
                files.append(("files", (path.name, handle)))
            for item in inline_attachments or []:
                path = Path(item["path"])
                handle = path.open("rb")
                opened.append(handle)
                files.append(("inline_files", (path.name, handle)))
            response = self.http.post(
                f"{self.base_url}/api/v1/mail/send",
                headers={"X-API-Key": self.token},
                data={
                    "to": json.dumps(to), "cc": json.dumps(cc or []),
                    "bcc": json.dumps(bcc or []), "subject": subject,
                    "html": body,
                },
                files=files, timeout=120,
            )
            if response.status_code >= 400:
                try:
                    detail = response.json().get("detail")
                except Exception:
                    detail = ""
                raise RuntimeError(detail or f"Error del backend (HTTP {response.status_code})")
            payload = response.json()
            return BackendMailResult(sender=str(payload.get("sender") or ""))
        finally:
            for handle in opened:
                handle.close()
