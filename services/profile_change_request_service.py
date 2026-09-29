from __future__ import annotations

import mimetypes
from io import BytesIO
from pathlib import Path

from PIL import Image, UnidentifiedImageError

from services.backend_client_service import BackendClientService
from services.company_logo_service import save_company_logo


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
            try:
                content, filename, content_type = (
                    self._backend.download_profile_change_logo(request_id)
                )
            except Exception as download_error:
                local = self._local_logo_for_request(item)
                if not local:
                    raise download_error
                local_path = Path(str(local.get("ruta_entrada") or ""))
                content = local_path.read_bytes()
                filename = str(local.get("nombre_original") or local_path.name)
                content_type = str(
                    local.get("mime_type")
                    or mimetypes.guess_type(filename)[0]
                    or "image/png"
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
        result = self._backend.review_profile_change_request(
            request_id,
            status="applied",
            note="Actualizado manualmente en A3 y aplicado desde Gest2A3Eco.",
        )
        self._discard_local_incoming_copy(item)
        return result

    def _local_logo_for_request(self, item: dict) -> dict | None:
        message_id = str(item.get("message_id") or "")
        if not message_id:
            return None
        local = self._gestor.get_adjunto_mensajeria_por_mensaje(message_id)
        if not local:
            return None
        path = Path(str(local.get("ruta_entrada") or ""))
        mime_type = str(local.get("mime_type") or "").lower()
        return local if path.is_file() and mime_type.startswith("image/") else None

    def _discard_local_incoming_copy(self, item: dict) -> None:
        """Retira la descarga temporal una vez creada la copia maestra."""
        local = self._local_logo_for_request(item)
        if not local:
            return
        try:
            self._gestor.no_guardar_adjunto_mensajeria(
                str(local.get("id") or ""), revisado_por="sistema",
            )
            Path(str(local.get("ruta_entrada") or "")).unlink(missing_ok=True)
        except Exception:
            # La solicitud ya esta aplicada; un fallo de limpieza no debe
            # revertir los datos maestros ni la confirmacion al cliente.
            return

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

        return save_company_logo(company_code, content)
