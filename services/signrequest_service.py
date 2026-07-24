from __future__ import annotations

import base64
from pathlib import Path

import requests


class SignRequestClient:
    """Cliente minimo y desacoplado para la API v1 de SignRequest."""

    def __init__(
        self,
        token: str,
        from_email: str,
        base_url: str = "https://signrequest.com/api/v1",
        timeout: int = 30,
        session=None,
    ):
        self.token = str(token or "").strip()
        self.from_email = str(from_email or "").strip()
        self.base_url = str(base_url or "").rstrip("/")
        self.timeout = int(timeout)
        self._http = session or requests.Session()
        if not self.token or not self.from_email:
            raise ValueError("Configura signrequest_token y signrequest_from_email.")

    def _request(self, method: str, path: str, **kwargs):
        headers = dict(kwargs.pop("headers", {}))
        headers["Authorization"] = f"Token {self.token}"
        response = self._http.request(
            method,
            f"{self.base_url}{path}",
            headers=headers,
            timeout=self.timeout,
            **kwargs,
        )
        if response.status_code >= 400:
            try:
                detail = response.json()
            except Exception:
                detail = response.text
            raise ValueError(f"SignRequest rechazo la operacion: {detail}")
        if response.status_code == 204:
            return {}
        return response.json()

    def enviar_documento(
        self,
        ruta: str,
        firmantes: list[dict],
        asunto: str,
        mensaje: str,
        external_id: str,
        callback_url: str = "",
        usar_sms: bool = False,
    ) -> dict:
        path = Path(ruta)
        if not path.is_file():
            raise FileNotFoundError(f"No se encuentra el documento para firma: {path}")
        signers = []
        for firmante in firmantes:
            email = str(firmante.get("email") or "").strip()
            if not email:
                raise ValueError("Todos los firmantes deben tener email.")
            item = {"email": email, "needs_to_sign": True, "order": int(firmante.get("order") or 0)}
            telefono = str(firmante.get("telefono") or "").strip()
            if usar_sms and telefono:
                item["verify_phone_number"] = telefono
            signers.append(item)
        payload = {
            "file_from_content": base64.b64encode(path.read_bytes()).decode("ascii"),
            "file_from_content_name": path.name,
            "name": asunto,
            "external_id": external_id,
            "from_email": self.from_email,
            "message": mensaje,
            "signers": signers,
            "send_reminders": True,
        }
        if callback_url:
            payload["events_callback_url"] = callback_url
        result = self._request("POST", "/signrequest-quick-create/", json=payload)
        return {
            "uuid": result.get("uuid") or result.get("signrequest_uuid") or "",
            "document": result.get("document") or "",
            "status": result.get("status") or "sent",
            "raw": result,
        }

    def consultar(self, request_id: str) -> dict:
        return self._request("GET", f"/signrequests/{request_id}/")

    def reenviar(self, request_id: str) -> dict:
        return self._request("POST", f"/signrequests/{request_id}/resend_signrequest_email/")

    def cancelar(self, request_id: str) -> dict:
        return self._request("POST", f"/signrequests/{request_id}/cancel_signrequest/")
