from __future__ import annotations

from io import BytesIO
from pathlib import Path

from PIL import Image, UnidentifiedImageError

from services.backend_client_service import BackendClientService
from utils.utilidades import get_document_repository_dir


class ProfileChangeRequestService:
    """Revisa solicitudes y aplica en escritorio la informacion aprobada."""

    def __init__(self, gestor, backend: BackendClientService | None = None):
        self._gestor = gestor
        self._backend = backend or BackendClientService()

    def list_pending(self) -> list[dict]:
        return self._backend.list_profile_change_requests("pending")

    def apply(self, item: dict) -> dict:
        request_id = str(item.get("id") or "")
        company_code = str(item.get("company_code") or "").strip().upper()
        if not request_id or not company_code:
            raise ValueError("La solicitud no identifica correctamente la empresa.")

        logo_path = None
        if item.get("has_logo"):
            content, filename, content_type = (
                self._backend.download_profile_change_logo(request_id)
            )
            logo_path = self._save_company_logo(
                company_code, content, filename, content_type,
            )

        updated = self._gestor.aplicar_cambios_empresa_solicitados(
            company_code,
            dict(item.get("changes") or {}),
            str(logo_path) if logo_path else None,
        )
        if not updated:
            raise ValueError(f"No existe la empresa {company_code} en el escritorio.")
        return self._backend.review_profile_change_request(
            request_id,
            status="applied",
            note="Aplicado y confirmado desde Gest2A3Eco.",
        )

    def reject(self, item: dict, note: str) -> dict:
        return self._backend.review_profile_change_request(
            str(item.get("id") or ""), status="rejected", note=note,
        )

    @staticmethod
    def _save_company_logo(
        company_code: str,
        content: bytes,
        filename: str,
        content_type: str,
    ) -> Path:
        if not content:
            raise ValueError("El archivo de logotipo esta vacio.")
        try:
            with Image.open(BytesIO(content)) as image:
                image.verify()
        except (UnidentifiedImageError, OSError) as exc:
            raise ValueError("El logotipo recibido no es una imagen valida.") from exc

        suffix = Path(filename or "").suffix.lower()
        allowed = {".png", ".jpg", ".jpeg", ".webp"}
        if suffix not in allowed:
            suffix = {
                "image/jpeg": ".jpg",
                "image/webp": ".webp",
            }.get(str(content_type).split(";", 1)[0].lower(), ".png")
        folder = (
            get_document_repository_dir()
            / "Empresas"
            / company_code
            / "Configuracion"
        )
        folder.mkdir(parents=True, exist_ok=True)
        target = folder / f"logotipo_empresa{suffix}"
        temporary = folder / f".logotipo_empresa{suffix}.tmp"
        temporary.write_bytes(content)
        temporary.replace(target)
        return target
