"""Autenticacion Microsoft Entra para usuarios de la aplicacion de escritorio."""

from __future__ import annotations

import requests

from utils.utilidades import load_app_config


class DesktopStaffAuthService:
    def __init__(self, config: dict | None = None, session=None):
        cfg = config or load_app_config()
        self.base_url = str(
            cfg.get("integrations_api_url") or cfg.get("dgt_api_url") or ""
        ).rstrip("/")
        self.http = session or requests.Session()

    @property
    def configured(self) -> bool:
        return bool(self.base_url)

    def login_microsoft(self) -> dict:
        if not self.configured:
            raise RuntimeError("El acceso Microsoft no esta configurado.")
        from services.desktop_oauth import run_oauth_flow

        result = run_oauth_flow(self.base_url, purpose="staff")
        if not result.success:
            raise RuntimeError(result.error or "Autenticacion cancelada")
        response = self.http.post(
            f"{self.base_url}/api/v1/desktop/staff-auth/exchange",
            json={"code": result.code},
            timeout=20,
        )
        response.raise_for_status()
        return response.json()
