from __future__ import annotations

import hashlib
import os
import re
import socket
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path

import requests

from utils.utilidades import get_document_repository_dir, load_app_config, save_app_config


@dataclass
class SyncAdjuntosResult:
    downloaded: list[str] = field(default_factory=list)
    existing: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


class MensajeriaRemoteClient:
    def __init__(self, *, user_id: int | str, user_name: str, config: dict | None = None, session=None):
        cfg = config or load_app_config()
        self.base_url = str(
            cfg.get("messaging_api_url") or cfg.get("integrations_api_url")
            or cfg.get("dgt_api_url") or ""
        ).rstrip("/")
        from utils.credential_store import (
            get_messaging_api_key,
            get_workstation_token, get_messaging_device_token,
        )
        # Autenticacion: MessagingApiKey especifica o WorkstationToken.
        # Las claves legacy (integrations_api_key, dgt_api_key) ya no se usan.
        self.api_key = (
            get_messaging_api_key()
            or get_workstation_token()
            or os.getenv("GEST2A3ECO_MESSAGING_API_KEY", "")
            or os.getenv("GEST2A3ECO_WORKSTATION_TOKEN", "")
            or ""
        )
        self.workstation = str(cfg.get("messaging_workstation_id") or socket.gethostname()).strip()
        self.device_token = (
            get_messaging_device_token()
            or os.getenv("GEST2A3ECO_MESSAGING_DEVICE_TOKEN", "")
            or ""
        )
        self.user_id = str(user_id)
        self.user_name = str(user_name or user_id)
        self.http = session or requests.Session()

    @property
    def configured(self) -> bool:
        return bool(self.base_url and self.api_key)

    def _headers(self) -> dict[str, str]:
        return {
            "X-API-Key": self.api_key, "X-Staff-Id": self.user_id,
            "X-Staff-Name": self.user_name, "X-Device-Id": self.workstation,
            "X-Device-Token": self.device_token,
        }

    def _url(self, path: str) -> str:
        if not self.configured:
            raise ValueError("Configura messaging_api_url y messaging_api_key.")
        return f"{self.base_url}/api/v1/messaging{path}"

    def sync_staff(
        self, role: str = "empleado", active: bool = True,
        channels: list[str] | None = None,
    ) -> None:
        self.ensure_device_enrolled()
        payload = {
            "external_id": self.user_id, "name": self.user_name,
            "role": role, "active": active,
        }
        if channels is not None:
            payload["channels"] = channels
        response = self.http.put(
            self._url(f"/internal/staff/{self.user_id}"), headers={"X-API-Key": self.api_key},
            json=payload, timeout=20,
        )
        response.raise_for_status()

    def ensure_device_enrolled(self) -> None:
        if self.device_token:
            return
        response = self.http.post(
            self._url(f"/internal/devices/{self.workstation}"),
            headers={"X-API-Key": self.api_key}, timeout=20,
        )
        response.raise_for_status()
        self.device_token = str(response.json()["device_token"])
        from utils.credential_store import store_messaging_device_token
        store_messaging_device_token(self.device_token)
        cfg = load_app_config()
        cfg["messaging_workstation_id"] = self.workstation
        save_app_config(cfg)

    def sync_organization(
        self, *, code: str, name: str,
        private_owner_id: str | None = None, active: bool = True,
    ) -> None:
        response = self.http.put(
            self._url(f"/internal/organizations/{code}"), headers={"X-API-Key": self.api_key},
            json={"company_code": code, "name": name, "private_owner_external_id": private_owner_id, "active": active}, timeout=20,
        )
        response.raise_for_status()

    def invite(self, *, code: str, name: str, email: str) -> dict:
        response = self.http.post(
            self._url("/internal/invitations"), headers={"X-API-Key": self.api_key},
            json={"company_code": code, "name": name, "email": email}, timeout=20,
        )
        response.raise_for_status()
        return response.json()

    def list_conversations(self) -> list[dict]:
        response = self.http.get(self._url("/staff/conversations"), headers=self._headers(), timeout=20)
        response.raise_for_status()
        return response.json()

    def company_conversation(self, company_code: str, kind: str) -> dict | None:
        code = str(company_code or "").strip().upper()
        channel = str(kind or "").strip().lower()
        return next((
            row for row in self.list_conversations()
            if str(row.get("company_code") or "").strip().upper() == code
            and str(row.get("kind") or "").strip().lower() == channel
        ), None)

    def list_messages(self, conversation_id: str) -> list[dict]:
        response = self.http.get(
            self._url(f"/staff/conversations/{conversation_id}/messages"), headers=self._headers(), timeout=20,
        )
        response.raise_for_status()
        rows = response.json()
        marked = self.http.post(
            self._url(f"/staff/conversations/{conversation_id}/read"), headers=self._headers(), timeout=20,
        )
        marked.raise_for_status()
        return rows

    def send_message(self, conversation_id: str, body: str, paths: list[str] | None = None) -> dict:
        opened = []
        try:
            files = []
            for raw in paths or []:
                handle = open(raw, "rb")
                opened.append(handle)
                files.append(("files", (Path(raw).name, handle)))
            response = self.http.post(
                self._url(f"/staff/conversations/{conversation_id}/messages"),
                headers=self._headers(), data={"body": body, "idempotency_key": str(uuid.uuid4())},
                files=files, timeout=120,
            )
            response.raise_for_status()
            return response.json()
        finally:
            for handle in opened:
                handle.close()

    def update_conversation(self, conversation_id: str, *, state: str | None = None, assigned_to: str | None = None) -> dict:
        payload = {}
        if state is not None:
            payload["state"] = state
        if assigned_to is not None:
            payload["assigned_staff_external_id"] = assigned_to
        response = self.http.patch(
            self._url(f"/staff/conversations/{conversation_id}"), headers=self._headers(), json=payload, timeout=20,
        )
        response.raise_for_status()
        return response.json()

    def download_audit(self, attachment_id: str) -> list[dict]:
        response = self.http.get(
            self._url(f"/staff/attachments/{attachment_id}/downloads"),
            headers=self._headers(), timeout=20,
        )
        response.raise_for_status()
        return response.json()

    def pending_attachments(self) -> list[dict]:
        response = self.http.get(self._url("/staff/attachments/pending"), headers=self._headers(), timeout=30)
        response.raise_for_status()
        return response.json()

    def listen_events(self, stop_event, on_event) -> None:
        """Mantiene el canal SSE del despacho y reconecta conservando cursor."""
        cursor = 0
        while not stop_event.is_set():
            try:
                with self.http.get(
                    self._url("/staff/events"), headers=self._headers(),
                    params={"after": cursor}, stream=True, timeout=(20, 45),
                ) as response:
                    response.raise_for_status()
                    event_id = None
                    event_type = "message"
                    data = ""
                    for raw in response.iter_lines(decode_unicode=True):
                        if stop_event.is_set():
                            return
                        line = str(raw or "")
                        if line.startswith("id:"):
                            event_id = int(line.split(":", 1)[1].strip())
                        elif line.startswith("event:"):
                            event_type = line.split(":", 1)[1].strip()
                        elif line.startswith("data:"):
                            data = line.split(":", 1)[1].strip()
                        elif not line and event_id is not None:
                            cursor = max(cursor, event_id)
                            on_event(event_type, data)
                            event_id, event_type, data = None, "message", ""
            except Exception:
                if not stop_event.is_set():
                    time.sleep(3)

    def download_pending_attachments(self, gestor) -> SyncAdjuntosResult:
        result = SyncAdjuntosResult()
        for item in self.pending_attachments():
            try:
                existing = gestor.get_adjunto_mensajeria_entrada(item["id"])
                if existing and Path(existing["ruta_entrada"]).is_file():
                    self._confirm(item["id"], existing["hash_archivo"])
                    result.existing.append(item["name"])
                    continue
                self._claim(item["id"])
                response = self.http.get(
                    self._url(f"/staff/attachments/{item['id']}/content"),
                    headers=self._headers(), params={"workstation": self.workstation}, timeout=120,
                )
                response.raise_for_status()
                content = response.content
                digest = hashlib.sha256(content).hexdigest()
                if digest != item["sha256"] or len(content) != int(item["size"]):
                    raise ValueError("El hash o el tamano descargado no coincide.")
                destination = self._destination(item["company_code"], item["id"], item["name"])
                temporary = destination.with_suffix(destination.suffix + ".part")
                temporary.write_bytes(content)
                os.replace(temporary, destination)
                gestor.upsert_adjunto_mensajeria_entrada({
                    "id": item["id"], "mensaje_remoto_id": item["message_id"],
                    "conversacion_remota_id": item["conversation_id"],
                    "codigo_empresa": item["company_code"], "empresa_nombre": item["company_name"],
                    "nombre_original": item["name"], "ruta_entrada": str(destination),
                    "hash_archivo": digest, "tamano": item["size"], "mime_type": item["content_type"],
                    "remitente": item.get("author_name") or "Cliente",
                })
                self._confirm(item["id"], digest)
                result.downloaded.append(item["name"])
            except Exception as exc:
                result.errors.append(f"{item.get('name') or item.get('id')}: {exc}")
        return result

    def _claim(self, attachment_id: str) -> None:
        response = self.http.post(
            self._url(f"/staff/attachments/{attachment_id}/claim"), headers=self._headers(),
            data={"workstation": self.workstation}, timeout=20,
        )
        response.raise_for_status()

    def _confirm(self, attachment_id: str, digest: str) -> None:
        response = self.http.post(
            self._url(f"/staff/attachments/{attachment_id}/confirm-local"), headers=self._headers(),
            data={"workstation": self.workstation, "sha256": digest}, timeout=30,
        )
        response.raise_for_status()

    @staticmethod
    def _destination(company_code: str, attachment_id: str, name: str) -> Path:
        safe = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", Path(name).name).strip(". ") or "adjunto"
        digits = "".join(ch for ch in str(company_code) if ch.isdigit())
        company = f"E{digits.zfill(5)[:5]}"
        directory = get_document_repository_dir() / "Entrada" / "Mensajeria" / company
        directory.mkdir(parents=True, exist_ok=True)
        return directory / f"{attachment_id}_{safe}"
