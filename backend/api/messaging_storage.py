from __future__ import annotations

import re
import uuid
from pathlib import Path

from backend.api.config import get_settings


def safe_name(value: str) -> str:
    return re.sub(r'[^A-Za-z0-9._-]', "_", Path(value or "adjunto").name)[:180] or "adjunto"


class MessagingStorage:
    """Almacen temporal. Azure en produccion y disco privado en desarrollo."""

    def __init__(self):
        self.cfg = get_settings()
        self._container = None
        if self.cfg.messaging_azure_connection_string:
            from azure.core.exceptions import ResourceExistsError
            from azure.storage.blob import BlobServiceClient

            service = BlobServiceClient.from_connection_string(
                self.cfg.messaging_azure_connection_string,
            )
            self._container = service.get_container_client(
                self.cfg.messaging_azure_container,
            )
            try:
                self._container.create_container()
            except ResourceExistsError:
                pass

    def put(self, content: bytes, filename: str) -> str:
        key = f"{uuid.uuid4().hex}/{safe_name(filename)}"
        if self._container is not None:
            self._container.upload_blob(key, content, overwrite=False)
        else:
            path = Path(self.cfg.messaging_storage_dir).resolve() / key
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(content)
        return key

    def get(self, key: str) -> bytes:
        if self._container is not None:
            return self._container.download_blob(key).readall()
        root = Path(self.cfg.messaging_storage_dir).resolve()
        path = (root / key).resolve()
        if root not in path.parents:
            raise ValueError("Ruta de almacenamiento no valida.")
        return path.read_bytes()

    def delete(self, key: str) -> None:
        if not key:
            return
        if self._container is not None:
            self._container.delete_blob(key, delete_snapshots="include")
            return
        root = Path(self.cfg.messaging_storage_dir).resolve()
        path = (root / key).resolve()
        if root not in path.parents:
            raise ValueError("Ruta de almacenamiento no valida.")
        path.unlink(missing_ok=True)
