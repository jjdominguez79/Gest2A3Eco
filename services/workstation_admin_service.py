"""Servicio de administracion de puestos de trabajo.

Comunica el escritorio con los endpoints /api/v1/desktop/admin/workstations
del backend. La autenticacion se basa en sesiones temporales de administrador
(no utiliza DGT_INTERNAL_API_KEY).
"""
from __future__ import annotations

import logging
import os
import socket

import requests

from utils.credential_store import (
    get_workstation_token,
    store_workstation_token,
    delete_workstation_token,
)
from utils.utilidades import load_app_config

logger = logging.getLogger(__name__)

# Posibles estados del puesto actual
STATUS_ACTIVATED = "activated"
STATUS_NOT_ACTIVATED = "not_activated"
STATUS_TOKEN_INVALID = "token_invalid"
STATUS_DEACTIVATED = "deactivated"
STATUS_BACKEND_UNAVAILABLE = "backend_unavailable"


def get_hostname() -> str:
    """Nombre del equipo actual (Windows hostname)."""
    return socket.gethostname()


class WorkstationAdminService:
    """Cliente HTTP para gestionar puestos desde el escritorio."""

    def __init__(self, config: dict | None = None):
        cfg = config or load_app_config()
        self.base_url = str(
            cfg.get("integrations_api_url") or cfg.get("dgt_api_url") or ""
        ).rstrip("/")
        self._session_token: str | None = None
        self._http = requests.Session()

    @property
    def configured(self) -> bool:
        return bool(self.base_url)

    def _admin_headers(self) -> dict:
        return {"Authorization": f"Bearer {self._session_token or ''}"}

    # ── Autenticacion admin ──────────────────────────────────────────────

    def login(self, username: str, password: str) -> dict:
        """
        Autentica al administrador en el backend.
        Almacena el token de sesion internamente (solo en memoria).
        Devuelve {"session_token": ..., "username": ..., "expires_at": ...}.
        Lanza requests.HTTPError si falla.
        """
        url = f"{self.base_url}/api/v1/desktop/auth/login"
        resp = self._http.post(url, json={"username": username, "password": password}, timeout=15)
        resp.raise_for_status()
        data = resp.json()
        self._session_token = data.get("session_token")
        return data

    @property
    def authenticated(self) -> bool:
        return bool(self._session_token)

    # ── Listado ──────────────────────────────────────────────────────────

    def list_workstations(self) -> list[dict]:
        """Lista todos los puestos registrados."""
        url = f"{self.base_url}/api/v1/desktop/admin/workstations"
        resp = self._http.get(url, headers=self._admin_headers(), timeout=15)
        resp.raise_for_status()
        return resp.json()

    # ── Crear puesto ─────────────────────────────────────────────────────

    def create_workstation(self, name: str) -> dict:
        """
        Crea un nuevo puesto. Devuelve dict con 'token' (plano, una sola vez).
        """
        url = f"{self.base_url}/api/v1/desktop/admin/workstations"
        resp = self._http.post(url, headers=self._admin_headers(), json={"name": name}, timeout=15)
        resp.raise_for_status()
        return resp.json()

    # ── Activar/Desactivar ───────────────────────────────────────────────

    def set_active(self, workstation_id: str, active: bool) -> dict:
        """Activa o desactiva un puesto."""
        url = f"{self.base_url}/api/v1/desktop/admin/workstations/{workstation_id}"
        resp = self._http.patch(url, headers=self._admin_headers(), json={"active": active}, timeout=15)
        resp.raise_for_status()
        return resp.json()

    # ── Regenerar token ──────────────────────────────────────────────────

    def regenerate_token(self, workstation_id: str) -> dict:
        """
        Regenera el token de un puesto. Invalida el token anterior.
        Devuelve dict con 'token' (plano, una sola vez).
        """
        url = f"{self.base_url}/api/v1/desktop/admin/workstations/{workstation_id}/regenerate-token"
        resp = self._http.post(url, headers=self._admin_headers(), timeout=15)
        resp.raise_for_status()
        return resp.json()

    # ── Verificar token actual ───────────────────────────────────────────

    def verify_token(self, token: str) -> dict:
        """
        Verifica si un workstation_token es valido.
        Devuelve {"valid": bool, "status": str, "name": str?}.
        """
        url = f"{self.base_url}/api/v1/desktop/admin/workstations/verify-token"
        resp = self._http.post(
            url, headers=self._admin_headers(),
            json={"workstation_token": token}, timeout=15,
        )
        resp.raise_for_status()
        return resp.json()

    # ── Estado del equipo actual ─────────────────────────────────────────

    def check_current_workstation_status(self) -> dict:
        """
        Determina el estado del puesto actual sin necesidad de sesion admin.

        Devuelve {"status": str, "name": str}.
        Posibles status:
          - activated: token valido y puesto activo
          - not_activated: no hay token almacenado
          - token_invalid: hay token pero no es valido
          - deactivated: hay token valido pero puesto desactivado
          - backend_unavailable: no se puede contactar con el backend
        """
        hostname = get_hostname()
        token = get_workstation_token() or os.getenv("GEST2A3ECO_WORKSTATION_TOKEN", "")
        if not token:
            return {"status": STATUS_NOT_ACTIVATED, "name": hostname}

        if not self.base_url:
            return {"status": STATUS_BACKEND_UNAVAILABLE, "name": hostname}

        try:
            # Usar el endpoint de autenticacion normal para verificar
            url = f"{self.base_url}/api/v1/sync"
            resp = self._http.get(
                url, headers={"X-API-Key": token},
                params={"updated_since": "2099-01-01T00:00:00"},
                timeout=10,
            )
            if resp.status_code == 200:
                return {"status": STATUS_ACTIVATED, "name": hostname}
            elif resp.status_code == 401:
                detail = ""
                try:
                    detail = resp.json().get("detail", "")
                except Exception:
                    pass
                if "no valida" in detail.lower() or "not valid" in detail.lower():
                    return {"status": STATUS_TOKEN_INVALID, "name": hostname}
                return {"status": STATUS_TOKEN_INVALID, "name": hostname}
            else:
                return {"status": STATUS_BACKEND_UNAVAILABLE, "name": hostname}
        except requests.ConnectionError:
            return {"status": STATUS_BACKEND_UNAVAILABLE, "name": hostname}
        except requests.Timeout:
            return {"status": STATUS_BACKEND_UNAVAILABLE, "name": hostname}
        except Exception:
            return {"status": STATUS_BACKEND_UNAVAILABLE, "name": hostname}

    # ── Activar este equipo (flujo completo) ─────────────────────────────

    def activate_current_workstation(self) -> dict:
        """
        Activa el equipo actual:
        1. Detecta hostname
        2. Busca si ya existe un puesto con ese nombre
        3. Si no existe, lo crea
        4. Guarda el token en Windows Credential Manager
        5. Devuelve resultado

        Requiere sesion admin previa (login()).
        Devuelve {"success": bool, "message": str, "workstation": dict?}.
        """
        hostname = get_hostname()

        # Comprobar si ya existe un puesto con este nombre
        workstations = self.list_workstations()
        existing = next((ws for ws in workstations if ws["name"] == hostname), None)

        if existing:
            # Ya existe: comprobar si tenemos token valido
            token = get_workstation_token()
            if token:
                verify = self.verify_token(token)
                if verify.get("valid") and verify.get("name") == hostname:
                    return {
                        "success": True,
                        "message": "Este equipo ya esta activado y tiene acceso al backend.",
                        "workstation": existing,
                        "already_active": True,
                    }

            # Existe pero no tenemos token valido o el puesto esta desactivado
            if not existing["active"]:
                # Reactivar
                self.set_active(existing["id"], True)
                existing["active"] = True

            # Regenerar token para este equipo
            result = self.regenerate_token(existing["id"])
            new_token = result.get("token", "")
            if not new_token:
                return {"success": False, "message": "El backend no devolvio un token."}
            ok = store_workstation_token(new_token)
            if not ok:
                return {
                    "success": False,
                    "message": "No se pudo guardar el token en Windows Credential Manager.",
                }
            logger.info("Token de puesto regenerado y almacenado para %s.", hostname)
            return {
                "success": True,
                "message": "Puesto reactivado correctamente.",
                "workstation": existing,
            }

        # No existe: crear nuevo puesto
        result = self.create_workstation(hostname)
        new_token = result.get("token", "")
        if not new_token:
            return {"success": False, "message": "El backend no devolvio un token."}
        ok = store_workstation_token(new_token)
        if not ok:
            return {
                "success": False,
                "message": "No se pudo guardar el token en Windows Credential Manager.",
            }
        logger.info("Puesto '%s' creado y token almacenado.", hostname)
        return {
            "success": True,
            "message": "Puesto activado correctamente.",
            "workstation": result,
        }
