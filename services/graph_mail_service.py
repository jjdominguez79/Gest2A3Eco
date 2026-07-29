from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import quote

import msal
import requests

from utils.utilidades import get_default_templates_dir, load_app_config


GRAPH_ROOT = "https://graph.microsoft.com/v1.0"
SCOPES = ["User.Read", "Mail.Send", "Mail.Send.Shared", "Mail.Read", "Mail.Read.Shared"]


@dataclass(frozen=True)
class GraphSendResult:
    message_id: str
    internet_message_id: str
    sender: str


@dataclass(frozen=True)
class GraphSyncResult:
    messages: list[dict]
    delta_link: str
    mailbox: str


class GraphMailService:
    """Envio delegado con Microsoft Graph; nunca almacena contraseñas."""

    def __init__(self, config: dict | None = None, session=None):
        cfg = config or (load_app_config().get("microsoft_graph") or {})
        self.tenant_id = str(cfg.get("tenant_id") or "").strip()
        self.client_id = str(cfg.get("client_id") or "").strip()
        self.shared_mailbox = str(cfg.get("shared_mailbox") or "Oficina@gestinem.es").strip()
        self.session = session or requests.Session()
        self._cache = msal.SerializableTokenCache()
        self._cache_path = Path(get_default_templates_dir()) / "graph_token_cache.bin"
        self._load_cache()

    def configured(self) -> bool:
        return bool(self.tenant_id and self.client_id)

    def _load_cache(self) -> None:
        try:
            if self._cache_path.exists():
                raw = self._cache_path.read_bytes()
                try:
                    import win32crypt
                    raw = win32crypt.CryptUnprotectData(raw, None, None, None, 0)[1]
                except ImportError:
                    pass
                self._cache.deserialize(raw.decode("utf-8"))
        except Exception:
            pass

    def _save_cache(self) -> None:
        if not self._cache.has_state_changed:
            return
        self._cache_path.parent.mkdir(parents=True, exist_ok=True)
        raw = self._cache.serialize().encode("utf-8")
        try:
            import win32crypt
            raw = win32crypt.CryptProtectData(raw, "Gest2A3Eco Graph", None, None, None, 0)
        except ImportError:
            pass
        self._cache_path.write_bytes(raw)

    def _token(self) -> tuple[str, str]:
        if not self.configured():
            raise ValueError("Microsoft Graph no esta configurado (tenant_id/client_id).")
        app = msal.PublicClientApplication(
            self.client_id,
            authority=f"https://login.microsoftonline.com/{self.tenant_id}",
            token_cache=self._cache,
        )
        accounts = app.get_accounts()
        result = app.acquire_token_silent(SCOPES, account=accounts[0]) if accounts else None
        if not result:
            result = app.acquire_token_interactive(scopes=SCOPES, prompt="select_account")
        self._save_cache()
        if "access_token" not in result:
            raise RuntimeError(result.get("error_description") or "Microsoft no ha autorizado el acceso.")
        username = str((result.get("id_token_claims") or {}).get("preferred_username") or "")
        return result["access_token"], username

    @staticmethod
    def _recipients(values: list[str]) -> list[dict]:
        return [{"emailAddress": {"address": value.strip()}} for value in values if value.strip()]

    def send(
        self, *, sender: str, to: list[str], subject: str, body: str,
        cc: list[str] | None = None, bcc: list[str] | None = None,
        attachments: list[str] | None = None,
        inline_attachments: list[dict] | None = None,
    ) -> GraphSendResult:
        token, signed_in = self._token()
        actual_sender = signed_in if sender == "me" else (sender or self.shared_mailbox)
        target = "me" if sender == "me" else f"users/{quote(actual_sender)}"
        message: dict = {
            "subject": subject,
            "body": {"contentType": "HTML", "content": body},
            "toRecipients": self._recipients(to),
            "ccRecipients": self._recipients(cc or []),
            "bccRecipients": self._recipients(bcc or []),
        }
        encoded_attachments = []
        import base64
        for raw_path in attachments or []:
            path = Path(raw_path)
            if not path.is_file():
                raise FileNotFoundError(f"No existe el adjunto: {path}")
            encoded_attachments.append({
                "@odata.type": "#microsoft.graph.fileAttachment",
                "name": path.name,
                "contentBytes": base64.b64encode(path.read_bytes()).decode("ascii"),
            })
        for item in inline_attachments or []:
            path = Path(str(item.get("path") or ""))
            if not path.is_file():
                raise FileNotFoundError(f"No existe la imagen incrustada: {path}")
            encoded_attachments.append({
                "@odata.type": "#microsoft.graph.fileAttachment",
                "name": path.name,
                "contentBytes": base64.b64encode(path.read_bytes()).decode("ascii"),
                "isInline": True,
                "contentId": str(item.get("content_id") or path.stem),
            })
        if encoded_attachments:
            message["attachments"] = encoded_attachments

        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "Prefer": 'IdType="ImmutableId"',
        }
        sent = self.session.post(
            f"{GRAPH_ROOT}/{target}/sendMail", headers=headers,
            data=json.dumps({"message": message, "saveToSentItems": True}), timeout=45,
        )
        if sent.status_code != 202:
            raise RuntimeError(self._error(sent))
        return GraphSendResult(
            message_id="",
            internet_message_id="",
            sender=actual_sender,
        )

    def sync_inbox(
        self, *, mailbox: str = "me", delta_link: str = "",
    ) -> GraphSyncResult:
        token, signed_in = self._token()
        actual_mailbox = signed_in if mailbox == "me" else mailbox
        target = "me" if mailbox == "me" else f"users/{quote(actual_mailbox)}"
        url = delta_link or (
            f"{GRAPH_ROOT}/{target}/mailFolders/inbox/messages/delta"
            "?changeType=created"
            "&$select=id,conversationId,internetMessageId,subject,body,"
            "from,toRecipients,ccRecipients,receivedDateTime,hasAttachments,isRead"
        )
        headers = {
            "Authorization": f"Bearer {token}",
            "Prefer": 'IdType="ImmutableId", outlook.body-content-type="html"',
        }
        messages: list[dict] = []
        final_delta = delta_link
        while url:
            response = self.session.get(url, headers=headers, timeout=45)
            if response.status_code != 200:
                raise RuntimeError(self._error(response))
            payload = response.json()
            messages.extend(
                item for item in payload.get("value", [])
                if "@removed" not in item
            )
            url = payload.get("@odata.nextLink") or ""
            final_delta = payload.get("@odata.deltaLink") or final_delta
        return GraphSyncResult(messages, final_delta, actual_mailbox)

    def list_attachments(self, *, mailbox: str, message_id: str) -> list[dict]:
        """Devuelve los adjuntos de archivo de un correo, sin descargarlos aun."""
        token, signed_in = self._token()
        actual_mailbox = signed_in if mailbox == "me" else mailbox
        target = "me" if mailbox == "me" else f"users/{quote(actual_mailbox)}"
        url = (
            f"{GRAPH_ROOT}/{target}/messages/{quote(str(message_id), safe='')}/attachments"
            "?$select=id,name,size,contentType,isInline"
        )
        response = self.session.get(url, headers={
            "Authorization": f"Bearer {token}",
            "Prefer": 'IdType="ImmutableId"',
        }, timeout=45)
        if response.status_code != 200:
            raise RuntimeError(self._error(response))
        return [
            item for item in response.json().get("value", [])
            if item.get("@odata.type") == "#microsoft.graph.fileAttachment"
            and not item.get("isInline", False)
        ]

    def download_attachment(self, *, mailbox: str, message_id: str, attachment_id: str) -> dict:
        """Descarga un adjunto de archivo; Graph lo entrega codificado en base64."""
        token, signed_in = self._token()
        actual_mailbox = signed_in if mailbox == "me" else mailbox
        target = "me" if mailbox == "me" else f"users/{quote(actual_mailbox)}"
        url = (
            f"{GRAPH_ROOT}/{target}/messages/{quote(str(message_id), safe='')}/attachments/"
            f"{quote(str(attachment_id), safe='')}"
        )
        response = self.session.get(url, headers={
            "Authorization": f"Bearer {token}",
            "Prefer": 'IdType="ImmutableId"',
        }, timeout=45)
        if response.status_code != 200:
            raise RuntimeError(self._error(response))
        item = response.json()
        if item.get("@odata.type") != "#microsoft.graph.fileAttachment" or not item.get("contentBytes"):
            raise ValueError("El adjunto no es un archivo descargable.")
        return item

    @staticmethod
    def _error(response) -> str:
        try:
            detail = response.json().get("error", {})
            return detail.get("message") or f"Graph HTTP {response.status_code}"
        except Exception:
            return f"Graph HTTP {response.status_code}: {response.text[:300]}"
