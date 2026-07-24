from __future__ import annotations

from typing import Protocol

import requests


class DgtRepository(Protocol):
    def listar_expedientes(self) -> list[dict]:
        ...

    def get_expediente(self, expediente_id: str) -> dict | None:
        ...

    def get_expediente_por_referencia(self, referencia: str) -> dict | None:
        ...

    def upsert_expediente(self, expediente: dict) -> str:
        ...

    def validar_expediente(self, expediente_id: str, user_id: int) -> None:
        ...

    def insertar_documento_generado(self, doc: dict) -> int:
        ...

    def listar_documentos_generados(self, expediente_id: str) -> list[dict]:
        ...

    def eliminar_expediente(self, expediente_id: str) -> None:
        ...

    def eliminar_documento_generado(self, documento_id) -> dict | None:
        ...


class SQLiteDgtRepository:
    """
    Adaptador SQLite actual para Trámites DGT.

    Mantiene el servicio desacoplado del gestor concreto para poder sustituirlo
    por una API online o un repositorio híbrido sin cambiar la UI.
    """

    def __init__(self, gestor):
        self._gestor = gestor

    def listar_expedientes(self) -> list[dict]:
        return self._gestor.listar_dgt_expedientes()

    def get_expediente(self, expediente_id: str) -> dict | None:
        return self._gestor.get_dgt_expediente(expediente_id)

    def get_expediente_por_referencia(self, referencia: str) -> dict | None:
        return self._gestor.get_dgt_expediente_por_referencia(referencia)

    def upsert_expediente(self, expediente: dict) -> str:
        return self._gestor.upsert_dgt_expediente(expediente)

    def validar_expediente(self, expediente_id: str, user_id: int) -> None:
        return self._gestor.validar_dgt_expediente(expediente_id, user_id)

    def insertar_documento_generado(self, doc: dict) -> int:
        return self._gestor.insertar_dgt_documento_generado(doc)

    def listar_documentos_generados(self, expediente_id: str) -> list[dict]:
        return self._gestor.listar_dgt_documentos_generados(expediente_id)

    def eliminar_expediente(self, expediente_id: str) -> None:
        self._gestor.eliminar_dgt_expediente(expediente_id)

    def eliminar_documento_generado(self, documento_id) -> dict | None:
        return self._gestor.eliminar_dgt_documento_generado(documento_id)


class ApiDgtRepository:
    """Adaptador HTTP. La API online es la fuente oficial del modulo DGT."""

    online = True

    def __init__(self, base_url: str, api_key: str, timeout: int = 20, session=None):
        self.base_url = str(base_url or "").rstrip("/")
        self.api_key = str(api_key or "")
        if not self.base_url or not self.api_key:
            raise ValueError("Configura dgt_api_url y dgt_api_key para usar Tramites DGT online.")
        self.timeout = timeout
        self._http = session or requests.Session()

    def _request(self, method: str, path: str, **kwargs):
        headers = dict(kwargs.pop("headers", {}))
        headers["X-API-Key"] = self.api_key
        response = self._http.request(
            method, f"{self.base_url}{path}", headers=headers, timeout=self.timeout, **kwargs
        )
        if response.status_code == 409:
            raise RuntimeError("El expediente ha cambiado en el servidor. Actualiza antes de guardar.")
        response.raise_for_status()
        if response.status_code == 204:
            return None
        return response.json()

    def _legacy(self, item: dict) -> dict:
        partes = item.get("partes") or {}
        vendedor = partes.get("vendedor") or {}
        comprador = partes.get("comprador") or {}
        vehiculo = item.get("vehiculo") or {}
        operacion = item.get("operacion") or {}
        return {
            **item,
            "vendedor_nombre": vendedor.get("nombre", ""),
            "vendedor_email": vendedor.get("email", ""),
            "vendedor_telefono": vendedor.get("telefono", ""),
            "vendedor_payload": {**(vendedor.get("datos") or {}), "nif": vendedor.get("nif", "")},
            "vendedor_estado": vendedor.get("estado", "pendiente"),
            "comprador_nombre": comprador.get("nombre", ""),
            "comprador_email": comprador.get("email", ""),
            "comprador_telefono": comprador.get("telefono", ""),
            "comprador_payload": {**(comprador.get("datos") or {}), "nif": comprador.get("nif", "")},
            "comprador_estado": comprador.get("estado", "pendiente"),
            "vehiculo_matricula": vehiculo.get("matricula", ""),
            "vehiculo_bastidor": vehiculo.get("bastidor", ""),
            "precio_venta": operacion.get("precio_venta"),
            "fecha_operacion": operacion.get("fecha_operacion", ""),
            "documentos": item.get("documentos") or [],
        }

    def create_expediente(self, payload: dict) -> str:
        created = self._request(
            "POST",
            "/api/v1/expedientes",
            json={
                "titulo": payload.get("titulo", ""),
                "responsable": payload.get("responsable", ""),
                "observaciones": payload.get("observaciones", ""),
                "vendedor_email": payload.get("vendedor_email", ""),
                "vendedor_telefono": payload.get("vendedor_telefono", ""),
                "comprador_email": payload.get("comprador_email", ""),
                "comprador_telefono": payload.get("comprador_telefono", ""),
            },
        )
        return created["id"]

    def listar_expedientes(self) -> list[dict]:
        return [self._legacy(item) for item in self._request("GET", "/api/v1/expedientes")]

    def get_expediente(self, expediente_id: str) -> dict | None:
        try:
            return self._legacy(self._request("GET", f"/api/v1/expedientes/{expediente_id}"))
        except requests.HTTPError as exc:
            if exc.response is not None and exc.response.status_code == 404:
                return None
            raise

    def get_expediente_por_referencia(self, referencia: str) -> dict | None:
        for item in self.listar_expedientes():
            if item.get("referencia") == referencia:
                return item
        return None

    def upsert_expediente(self, expediente: dict) -> str:
        expediente_id = expediente.get("id")
        if not expediente_id:
            return self.create_expediente(expediente)
        self._request(
            "PATCH",
            f"/api/v1/expedientes/{expediente_id}",
            json={
                "titulo": expediente.get("titulo", ""),
                "estado": expediente.get("estado", "borrador"),
                "responsable": expediente.get("responsable", ""),
                "observaciones": expediente.get("observaciones", ""),
                "version": expediente.get("version"),
            },
        )
        return expediente_id

    def create_links(self, expediente_id: str) -> dict[str, str]:
        data = self._request("POST", f"/api/v1/expedientes/{expediente_id}/links")
        return {rol: item["url"] for rol, item in data.items()}

    def revoke_link(self, expediente_id: str, rol: str) -> None:
        self._request("POST", f"/api/v1/expedientes/{expediente_id}/links/{rol}/revoke")

    def sync(self, updated_since: str = "") -> list[dict]:
        params = {"updated_since": updated_since} if updated_since else {}
        return [self._legacy(item) for item in self._request("GET", "/api/v1/sync", params=params)]

    def update_parte(self, expediente_id: str, rol: str, payload: dict) -> None:
        datos = dict(payload)
        top = {key: datos.pop(key, "") for key in ("tipo_persona", "nombre", "nif", "email", "telefono")}
        self._request(
            "PATCH",
            f"/api/v1/expedientes/{expediente_id}/partes/{rol}",
            json={**top, "datos": datos},
        )

    def validar_expediente(self, expediente_id: str, user_id: int) -> None:
        self._request("POST", f"/api/v1/expedientes/{expediente_id}/validar")

    def insertar_documento_generado(self, doc: dict) -> str:
        return self._request(
            "POST", f"/api/v1/expedientes/{doc['expediente_id']}/documentos-generados", json=doc
        )["id"]

    def listar_documentos_generados(self, expediente_id: str) -> list[dict]:
        return self._request("GET", f"/api/v1/expedientes/{expediente_id}/documentos-generados")

    def listar_documentos_aportados(self, expediente_id: str) -> list[dict]:
        return self._request("GET", f"/api/v1/expedientes/{expediente_id}/documentos")

    def eliminar_expediente(self, expediente_id: str) -> None:
        self._request("DELETE", f"/api/v1/expedientes/{expediente_id}")

    def eliminar_documento_aportado(self, documento_id: str) -> None:
        self._request("DELETE", f"/api/v1/documentos/{documento_id}")

    def eliminar_documento_generado(self, documento_id: str) -> dict | None:
        return self._request("DELETE", f"/api/v1/documentos-generados/{documento_id}")

    def download_documento(self, documento_id: str, target_path: str) -> str:
        response = self._http.get(
            f"{self.base_url}/api/v1/documentos/{documento_id}/download",
            headers={"X-API-Key": self.api_key},
            timeout=self.timeout,
        )
        response.raise_for_status()
        with open(target_path, "wb") as fh:
            fh.write(response.content)
        return target_path
