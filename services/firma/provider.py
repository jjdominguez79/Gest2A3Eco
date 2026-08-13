from __future__ import annotations

from typing import Any, Protocol


class FirmaProvider(Protocol):
    def enviar_documento(self, ruta: str, firmantes: list[dict], asunto: str,
                         mensaje: str, external_id: str, callback_url: str = "",
                         usar_sms: bool = False) -> dict: ...

    def consultar(self, request_id: str) -> dict: ...

    def cancelar(self, request_id: str) -> dict: ...

    def eliminar(self, request_id: str) -> dict: ...

    def reenviar(self, request_id: str) -> dict: ...

    def descargar_evidencias(self, request_id: str, destino: str,
                             nombre_base: str) -> dict: ...


def build_firma_provider(cfg: dict[str, Any]) -> FirmaProvider | None:
    """Construye el proveedor de firma electronica via backend."""
    if not bool(cfg.get("firma_habilitada", True)):
        return None
    api_url = str(cfg.get("integrations_api_url") or cfg.get("dgt_api_url") or "").strip()
    from utils.credential_store import get_workstation_token, get_integrations_api_key
    import os
    api_key = (
        get_workstation_token()
        or get_integrations_api_key()
        or os.getenv("GEST2A3ECO_INTEGRATIONS_API_KEY", "")
        or os.getenv("GEST2A3ECO_DGT_API_KEY", "")
    )
    if api_url and api_key:
        from services.dgt_remote_integrations import BackendSignRequestClient

        return BackendSignRequestClient(api_url, api_key)
    return None
