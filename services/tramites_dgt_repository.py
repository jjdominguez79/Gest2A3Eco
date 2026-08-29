from __future__ import annotations

from pathlib import Path
from typing import Protocol

import requests

from services.tramites_dgt_documentos import mime_documento_dgt


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


class ApiDgtRepository:
    """Adaptador HTTP. La API online es la fuente oficial del modulo DGT."""

    online = True

    def __init__(self, base_url: str, api_key: str, timeout: int = 20, session=None,
                 workstation_token: str = ""):
        self.base_url = str(base_url or "").rstrip("/")
        # Preferir workstation_token si esta disponible
        self.api_key = str(workstation_token or api_key or "")
        if not self.base_url or not self.api_key:
            raise ValueError("Configura integrations_api_url y workstation_token para usar Tramites DGT online.")
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
        if response.status_code >= 400:
            try:
                detail = response.json().get("detail")
            except Exception:
                detail = None
            if isinstance(detail, list):
                detail = "\n".join(str(item) for item in detail)
            if detail:
                raise ValueError(str(detail))
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
            "vendedor_payload": {
                **(vendedor.get("datos") or {}),
                **{key: vendedor.get(key, "") for key in ("tipo_persona", "nombre", "nif", "email", "telefono")},
            },
            "vendedor_estado": vendedor.get("estado", "pendiente"),
            "comprador_nombre": comprador.get("nombre", ""),
            "comprador_email": comprador.get("email", ""),
            "comprador_telefono": comprador.get("telefono", ""),
            "comprador_payload": {
                **(comprador.get("datos") or {}),
                **{key: comprador.get(key, "") for key in ("tipo_persona", "nombre", "nif", "email", "telefono")},
            },
            "comprador_estado": comprador.get("estado", "pendiente"),
            "vehiculo_matricula": vehiculo.get("matricula", ""),
            "vehiculo_bastidor": vehiculo.get("bastidor", ""),
            "precio_venta": operacion.get("precio_venta"),
            "fecha_operacion": operacion.get("fecha_operacion", ""),
            "codigo_tasa": operacion.get("codigo_tasa", ""),
            "modelo_620_presentado": bool(operacion.get("modelo_620_presentado", False)),
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
                "vendedor_nombre": expediente.get("vendedor_nombre", ""),
                "vendedor_email": expediente.get("vendedor_email", ""),
                "vendedor_telefono": expediente.get("vendedor_telefono", ""),
                "comprador_nombre": expediente.get("comprador_nombre", ""),
                "comprador_email": expediente.get("comprador_email", ""),
                "comprador_telefono": expediente.get("comprador_telefono", ""),
                "vehiculo_matricula": expediente.get("vehiculo_matricula", ""),
                "vehiculo_bastidor": expediente.get("vehiculo_bastidor", ""),
                "precio_venta": expediente.get("precio_venta"),
                "fecha_operacion": expediente.get("fecha_operacion", ""),
                "codigo_tasa": expediente.get("codigo_tasa", ""),
                "modelo_620_presentado": bool(expediente.get("modelo_620_presentado", False)),
                "firma_estado": expediente.get("firma_estado"),
                "firma_provider": expediente.get("firma_provider"),
                "firma_request_id": expediente.get("firma_request_id"),
                "firma_evidencia": expediente.get("firma_evidencia"),
                "version": expediente.get("version"),
            },
        )
        return expediente_id

    def create_links(self, expediente_id: str) -> dict[str, str]:
        data = self._request("POST", f"/api/v1/expedientes/{expediente_id}/links")
        return {rol: item["url"] for rol, item in data.items()}

    def revoke_link(self, expediente_id: str, rol: str) -> None:
        self._request("POST", f"/api/v1/expedientes/{expediente_id}/links/{rol}/revoke")

    def finalizar_expediente(self, expediente_id: str) -> dict:
        return self._legacy(
            self._request("POST", f"/api/v1/expedientes/{expediente_id}/finalizar")
        )

    def solicitar_subsanacion(self, expediente_id: str, rol: str, mensaje: str) -> dict:
        return self._request(
            "POST",
            f"/api/v1/expedientes/{expediente_id}/subsanaciones",
            json={"rol": rol, "mensaje": mensaje},
        )

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

    def upload_documento(self, expediente_id: str, rol: str, tipo: str, file_path: str) -> dict:
        path = Path(file_path)
        filename = path.name
        mime_type = mime_documento_dgt(str(path))
        with open(file_path, "rb") as fh:
            return self._request(
                "POST",
                f"/api/v1/expedientes/{expediente_id}/documentos",
                data={"rol": rol, "tipo": tipo},
                files={"file": (filename, fh, mime_type)},
            )

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
