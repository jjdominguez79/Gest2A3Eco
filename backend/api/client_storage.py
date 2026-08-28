"""Almacen permanente de documentos del cliente.

Contenedor Azure privado separado del temporal de mensajeria.
Fallback a disco local para desarrollo.
"""

from __future__ import annotations

import hashlib
import re
import uuid
from pathlib import Path

from backend.api.config import get_settings


def _safe_name(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]", "_", Path(value or "documento").name)[:180] or "documento"


class ClientDocumentStorage:
    """Blob privado permanente para documentos del area del cliente."""

    def __init__(self, *, allow_local_fallback: bool | None = None) -> None:
        cfg = get_settings()
        self._conn_str = cfg.client_documents_azure_connection_string
        self._container_name = cfg.client_documents_azure_container
        self._local_dir = cfg.client_documents_storage_dir
        self._container = None

        # allow_local_fallback: None -> tomar del config; True/False -> forzar
        if allow_local_fallback is None:
            allow_local_fallback = cfg.client_documents_allow_local_storage

        if self._conn_str:
            from azure.core.exceptions import ResourceExistsError
            from azure.storage.blob import BlobServiceClient
            service = BlobServiceClient.from_connection_string(self._conn_str)
            self._container = service.get_container_client(self._container_name)
            try:
                self._container.create_container()
            except ResourceExistsError:
                pass
        elif not allow_local_fallback:
            raise RuntimeError(
                "CLIENT_DOCUMENTS_AZURE_CONNECTION_STRING es obligatorio. "
                "Para desarrollo o tests, establece CLIENT_DOCUMENTS_ALLOW_LOCAL_STORAGE=true."
            )

    def put(self, content: bytes, filename: str, *, organization_id: str = "") -> str:
        """Sube contenido y devuelve la clave del blob."""
        key = f"{organization_id}/{uuid.uuid4().hex}/{_safe_name(filename)}"
        if self._container is not None:
            self._container.upload_blob(key, content, overwrite=False)
        else:
            path = Path(self._local_dir).resolve() / key
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(content)
        return key

    def get(self, key: str) -> bytes:
        if self._container is not None:
            return self._container.download_blob(key).readall()
        root = Path(self._local_dir).resolve()
        path = (root / key).resolve()
        if root not in path.parents and path != root:
            raise ValueError("Ruta de almacenamiento no valida.")
        return path.read_bytes()

    def delete(self, key: str) -> None:
        if not key:
            return
        if self._container is not None:
            self._container.delete_blob(key, delete_snapshots="include")
            return
        root = Path(self._local_dir).resolve()
        path = (root / key).resolve()
        if root not in path.parents and path != root:
            raise ValueError("Ruta de almacenamiento no valida.")
        path.unlink(missing_ok=True)

    @staticmethod
    def compute_sha256(content: bytes) -> str:
        return hashlib.sha256(content).hexdigest()
