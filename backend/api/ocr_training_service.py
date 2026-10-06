"""Almacenamiento backend de ejemplos para entrenamiento OCR en Azure."""
from __future__ import annotations

import json
import re
from pathlib import Path

from backend.api.config import get_settings


def _segmento_seguro(value: str, fallback: str) -> str:
    limpio = re.sub(r"[^A-Za-z0-9._-]+", "_", str(value or "").strip())
    return limpio[:120] or fallback


def _nombres_blobs(empresa_id: str, ejemplo_id: str, filename: str) -> tuple[str, str]:
    """Genera nombres unicos visibles desde la raiz del proyecto de Studio."""
    empresa = _segmento_seguro(empresa_id, "empresa")
    ejemplo = _segmento_seguro(ejemplo_id, "ejemplo")
    nombre = _segmento_seguro(
        Path(filename or "documento.pdf").name,
        "documento.pdf",
    )
    identificador = f"gest2a3eco_{empresa}_{ejemplo}"
    return f"{identificador}_{nombre}", f"_metadata/{identificador}.json"


class OcrTrainingStorage:
    """Publica ejemplos en el Blob privado configurado solo en el backend."""

    def __init__(self) -> None:
        cfg = get_settings()
        connection_string = str(cfg.azure_ocr_training_connection_string or "").strip()
        self.container_name = str(cfg.azure_ocr_training_container or "").strip()
        if not connection_string or not self.container_name:
            raise RuntimeError("El almacenamiento de aprendizaje OCR no esta configurado.")

        from azure.core.exceptions import ResourceExistsError
        from azure.storage.blob import BlobServiceClient

        service = BlobServiceClient.from_connection_string(connection_string)
        self._container = service.get_container_client(self.container_name)
        try:
            self._container.create_container()
        except ResourceExistsError:
            pass

    def upload_example(
        self,
        *,
        content: bytes,
        filename: str,
        content_type: str,
        empresa_id: str,
        ejemplo_id: str,
        metadata: dict,
    ) -> dict:
        from azure.storage.blob import ContentSettings

        blob_name, metadata_name = _nombres_blobs(
            empresa_id,
            ejemplo_id,
            filename,
        )

        self._container.upload_blob(
            blob_name,
            content,
            overwrite=True,
            content_settings=ContentSettings(
                content_type=content_type or "application/octet-stream",
            ),
        )
        payload = dict(metadata or {})
        payload.update({
            "empresa_id": str(empresa_id),
            "ejemplo_id": str(ejemplo_id),
            "blob": blob_name,
        })
        self._container.upload_blob(
            metadata_name,
            json.dumps(payload, ensure_ascii=True, sort_keys=True).encode("utf-8"),
            overwrite=True,
            content_settings=ContentSettings(content_type="application/json"),
        )
        return {
            "blob": blob_name,
            "metadata_blob": metadata_name,
            "container": self.container_name,
        }
