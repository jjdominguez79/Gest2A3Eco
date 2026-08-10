from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from urllib.parse import quote

import msal
import requests
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.serialization import pkcs12


GRAPH_ROOT = "https://graph.microsoft.com/v1.0"


@dataclass(frozen=True)
class GraphSyncResult:
    messages: list[dict]
    delta_link: str


class GraphApplicationMailClient:
    def __init__(
        self,
        *,
        tenant_id: str,
        client_id: str,
        certificate_path: Path,
        certificate_password: str,
        session=None,
    ):
        private_key, certificate, _chain = pkcs12.load_key_and_certificates(
            certificate_path.read_bytes(),
            certificate_password.encode("utf-8"),
        )
        if private_key is None or certificate is None:
            raise ValueError("El PFX no contiene una clave privada y un certificado validos.")
        credential = {
            "private_key": private_key.private_bytes(
                serialization.Encoding.PEM,
                serialization.PrivateFormat.PKCS8,
                serialization.NoEncryption(),
            ).decode("ascii"),
            "thumbprint": certificate.fingerprint(hashes.SHA1()).hex(),
        }
        self._app = msal.ConfidentialClientApplication(
            client_id,
            authority=f"https://login.microsoftonline.com/{tenant_id}",
            client_credential=credential,
        )
        self._session = session or requests.Session()

    def _token(self) -> str:
        result = self._app.acquire_token_for_client(
            scopes=["https://graph.microsoft.com/.default"]
        )
        token = str(result.get("access_token") or "")
        if not token:
            raise RuntimeError(
                result.get("error_description")
                or result.get("error")
                or "Microsoft no ha emitido un token para el sincronizador."
            )
        return token

    def sync_inbox(self, *, mailbox: str, delta_link: str = "") -> GraphSyncResult:
        target = f"users/{quote(mailbox)}"
        url = delta_link or (
            f"{GRAPH_ROOT}/{target}/mailFolders/inbox/messages/delta"
            "?changeType=created"
            "&$select=id,conversationId,internetMessageId,subject,body,"
            "from,toRecipients,ccRecipients,receivedDateTime,hasAttachments,isRead"
        )
        headers = {
            "Authorization": f"Bearer {self._token()}",
            "Prefer": 'IdType="ImmutableId", outlook.body-content-type="html"',
        }
        messages: list[dict] = []
        final_delta = delta_link
        while url:
            response = self._session.get(url, headers=headers, timeout=45)
            if response.status_code != 200:
                raise RuntimeError(self._error(response))
            payload = response.json()
            messages.extend(
                item for item in payload.get("value", []) if "@removed" not in item
            )
            url = str(payload.get("@odata.nextLink") or "")
            final_delta = str(payload.get("@odata.deltaLink") or final_delta)
        if not final_delta:
            raise RuntimeError("Microsoft Graph no devolvio el delta de sincronizacion.")
        return GraphSyncResult(messages=messages, delta_link=final_delta)

    @staticmethod
    def _error(response) -> str:
        try:
            detail = response.json().get("error", {})
            return detail.get("message") or f"Graph HTTP {response.status_code}"
        except Exception:
            return f"Graph HTTP {response.status_code}: {response.text[:300]}"

