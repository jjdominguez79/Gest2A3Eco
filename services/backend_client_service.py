"""Servicio de publicacion de documentos y sincronizacion con el area de clientes.

El escritorio sube el PDF real por multipart al backend; el backend nunca
accede a rutas locales del puesto de trabajo.
"""

from __future__ import annotations

import os
from pathlib import Path

import requests

from utils.utilidades import load_app_config


class BackendClientService:
    """Comunica el escritorio con el backend para el area de clientes."""

    def __init__(self, config: dict | None = None, session=None):
        cfg = config or load_app_config()
        self.base_url = str(
            cfg.get("integrations_api_url") or cfg.get("dgt_api_url") or ""
        ).rstrip("/")
        from utils.credential_store import get_workstation_token
        self.token = get_workstation_token() or os.getenv("GEST2A3ECO_WORKSTATION_TOKEN", "")
        self.http = session or requests.Session()

    @property
    def configured(self) -> bool:
        return bool(self.base_url and self.token)

    def _headers(self) -> dict:
        return {"X-API-Key": self.token}

    def _ensure_configured(self) -> None:
        if not self.configured:
            raise ValueError(
                "La plataforma de clientes no esta configurada: revisa la URL "
                "de integraciones y el token de este puesto."
            )

    # ----- Publicacion documental -----

    def publish_document(
        self,
        *,
        source_type: str,
        source_id: str,
        source_version: int = 1,
        display_name: str,
        pdf_path: str,
        customer_tax_id: str = "",
        fiscal_year: int = 0,
        amount: float | None = None,
        document_date: str | None = None,
        description: str = "",
        expected_sha256: str = "",
    ) -> dict:
        """Sube un PDF al area documental del cliente por multipart."""
        self._ensure_configured()
        url = f"{self.base_url}/api/v1/messaging/client/documents/internal/publish"

        p = Path(pdf_path)
        if not p.is_file():
            raise FileNotFoundError(f"PDF no encontrado: {pdf_path}")

        fields = {
            "source_system": "desktop_invoice",
            "source_id": source_id,
            "source_version": str(source_version),
            "document_type": source_type,
            "display_name": display_name,
            "customer_tax_id": customer_tax_id,
            "fiscal_year": str(fiscal_year),
        }
        if expected_sha256:
            fields["expected_sha256"] = expected_sha256
        if amount is not None:
            fields["amount"] = str(amount)
        if document_date:
            fields["document_date"] = str(document_date)
        if description:
            fields["description"] = description

        # Necesitamos el organization_id; el backend lo resuelve por NIF
        # pero el endpoint /internal/publish necesita organization_id explícito.
        # Lo obtenemos via el endpoint de resolucion o lo incluimos como campo.
        # En la implementacion actual, pasamos customer_tax_id y el backend
        # busca la org por NIF.

        with open(pdf_path, "rb") as f:
            resp = self.http.post(
                url,
                headers=self._headers(),
                data=fields,
                files={"file": (p.name, f, "application/pdf")},
                timeout=60,
            )
        resp.raise_for_status()
        return resp.json()

    # ----- Sincronizacion de perfil empresarial -----

    def sync_company_profile(self, *, company_code: str, profile: dict) -> dict:
        """Sincroniza los datos del perfil de la empresa con el backend."""
        self._ensure_configured()
        url = f"{self.base_url}/api/v1/messaging/client/company-profile/internal/sync-profile"
        payload = {"company_code": company_code, **profile}
        resp = self.http.put(url, headers=self._headers(), json=payload, timeout=30)
        resp.raise_for_status()
        return resp.json()

    # ----- Sincronizacion de clientes/deudores -----

    def sync_customers(self, *, organization_id: str, customers: list[dict]) -> dict:
        """Sincroniza clientes del escritorio con la plataforma online."""
        self._ensure_configured()
        url = f"{self.base_url}/api/v1/messaging/client/invoicing/worker/customer-sync"
        resp = self.http.post(
            url,
            headers=self._headers(),
            json={"organization_id": organization_id, "customers": customers},
            timeout=60,
        )
        resp.raise_for_status()
        return resp.json()
