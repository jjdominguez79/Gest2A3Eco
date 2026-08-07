from __future__ import annotations

from typing import Any, Protocol


class FirmaProvider(Protocol):
    def enviar_documento(self, ruta: str, firmantes: list[dict], asunto: str,
                         mensaje: str, external_id: str, callback_url: str = "",
                         usar_sms: bool = False) -> dict: ...

    def consultar(self, request_id: str) -> dict: ...

    def cancelar(self, request_id: str) -> dict: ...

    def reenviar(self, request_id: str) -> dict: ...

    def descargar_evidencias(self, request_id: str, destino: str,
                             nombre_base: str) -> dict: ...


def build_firma_provider(cfg: dict[str, Any]) -> FirmaProvider | None:
    """Construye el proveedor sin exponer el token del puesto por defecto."""
    if not bool(cfg.get("firma_habilitada", True)):
        return None
    api_url = str(cfg.get("dgt_api_url") or "").strip()
    api_key = str(cfg.get("dgt_api_key") or "").strip()
    if api_url and api_key:
        from services.dgt_remote_integrations import BackendSignRequestClient

        return BackendSignRequestClient(api_url, api_key)
    if bool(cfg.get("firma_permitir_cliente_local")):
        token = str(cfg.get("signrequest_token") or "").strip()
        from_email = str(cfg.get("signrequest_from_email") or "").strip()
        if token and from_email:
            from services.signrequest_service import SignRequestClient

            return SignRequestClient(
                token, from_email, base_url=cfg.get("signrequest_base_url") or None,
            )
    return None
