from __future__ import annotations

import base64
import hashlib
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
            item = {"email": email, "needs_to_sign": True,
                    "order": int(firmante.get("order") or firmante.get("orden") or 0)}
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
        solicitud = self._request("GET", f"/signrequests/{request_id}/")
        document_url = str(solicitud.get("document") or "")
        if not document_url:
            return {"status": "desconocido", "solicitud": solicitud}
        documento = self._request_url("GET", document_url)
        signing_log = documento.get("signing_log") or {}
        if documento.get("pdf") and signing_log.get("pdf"):
            estado = "signed"
        elif documento.get("status"):
            estado = str(documento["status"])
        elif solicitud.get("is_being_prepared"):
            estado = "preparing"
        else:
            estado = "sent"
        return {
            "status": estado,
            "document_uuid": documento.get("uuid") or "",
            "signed_pdf_url": documento.get("pdf") or "",
            "signing_log_url": signing_log.get("pdf") or "",
            "security_hash": documento.get("security_hash") or "",
            "signing_log_security_hash": signing_log.get("security_hash") or "",
        }

    def descargar_evidencias(self, request_id: str, destino: str, nombre_base: str) -> dict:
        estado = self.consultar(request_id)
        if estado.get("status") != "signed":
            raise ValueError("La solicitud todavia no esta completamente firmada.")
        output = Path(destino)
        output.mkdir(parents=True, exist_ok=True)
        signed_path = output / f"{nombre_base}_firmado.pdf"
        log_path = output / f"{nombre_base}_registro_firma.pdf"
        self._download(estado["signed_pdf_url"], signed_path)
        self._download(estado["signing_log_url"], log_path)
        return {
            "ruta_firmado": str(signed_path),
            "ruta_registro_firma": str(log_path),
            "sha256_firmado": self._sha256(signed_path),
            "sha256_registro_firma": self._sha256(log_path),
            "security_hash": estado.get("security_hash") or "",
            "signing_log_security_hash": estado.get("signing_log_security_hash") or "",
            "document_uuid": estado.get("document_uuid") or "",
        }

    def _request_url(self, method: str, url: str):
        response = self._http.request(
            method,
            url,
            headers={"Authorization": f"Token {self.token}"},
            timeout=self.timeout,
        )
        if response.status_code >= 400:
            raise ValueError(f"SignRequest rechazo la consulta ({response.status_code}).")
        return response.json()

    def _download(self, url: str, path: Path) -> None:
        response = self._http.request("GET", url, timeout=self.timeout)
        if response.status_code >= 400:
            raise ValueError(f"No se pudo descargar una evidencia ({response.status_code}).")
        path.write_bytes(response.content)

    @staticmethod
    def _sha256(path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as fh:
            for chunk in iter(lambda: fh.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()

    def reenviar(self, request_id: str) -> dict:
        return self._request("POST", f"/signrequests/{request_id}/resend_signrequest_email/")

    def cancelar(self, request_id: str) -> dict:
        return self._request("POST", f"/signrequests/{request_id}/cancel_signrequest/")
