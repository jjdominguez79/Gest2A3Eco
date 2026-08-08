from __future__ import annotations

import hashlib
import re
import uuid
from pathlib import Path

from fastapi import HTTPException, UploadFile

from backend.dgt_api.config import get_settings

MAX_FILE_SIZE = 10 * 1024 * 1024
ALLOWED_TYPES = {
    "application/pdf": (".pdf", b"%PDF"),
    "image/jpeg": (".jpg", b"\xff\xd8\xff"),
    "image/png": (".png", b"\x89PNG\r\n\x1a\n"),
}


async def read_validated_upload(file: UploadFile) -> tuple[bytes, dict]:
    content_type = str(file.content_type or "").lower()
    rule = ALLOWED_TYPES.get(content_type)
    if not rule:
        raise HTTPException(415, "Solo se admiten PDF, JPG y PNG")
    data = await file.read(MAX_FILE_SIZE + 1)
    if not data or len(data) > MAX_FILE_SIZE:
        raise HTTPException(413, "El archivo supera el limite de 10 MB")
    extension, signature = rule
    if not data.startswith(signature):
        raise HTTPException(422, "El contenido no coincide con el tipo declarado")
    return data, {
        "nombre_archivo": Path(file.filename or f"documento{extension}").name,
        "content_type": content_type,
        "size": len(data),
        "sha256": hashlib.sha256(data).hexdigest(),
        "extension": extension,
    }


def save_private_upload_bytes(
    data: bytes, referencia: str, rol: str, metadata: dict,
) -> dict:
    safe_ref = re.sub(r"[^A-Za-z0-9_-]", "_", referencia)
    extension = str(
        metadata.get("extension")
        or Path(str(metadata.get("nombre_archivo") or "")).suffix
        or ".bin"
    )
    key = f"{safe_ref}/{rol}/{uuid.uuid4().hex}{extension}"
    root = Path(get_settings().storage_dir).resolve()
    target = (root / key).resolve()
    if root not in target.parents:
        raise HTTPException(400, "Ruta de almacenamiento no valida")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(data)
    return {
        "storage_key": key,
        "nombre_archivo": metadata["nombre_archivo"],
        "content_type": metadata["content_type"],
        "size": metadata["size"],
        "sha256": metadata["sha256"],
    }


async def save_private_upload(file: UploadFile, referencia: str, rol: str) -> dict:
    data, metadata = await read_validated_upload(file)
    return save_private_upload_bytes(data, referencia, rol, metadata)


def delete_private_upload(storage_key: str) -> bool:
    root = Path(get_settings().storage_dir).resolve()
    target = (root / str(storage_key or "")).resolve()
    if root not in target.parents:
        raise ValueError("Ruta de almacenamiento no valida")
    if not target.is_file():
        return False
    target.unlink()
    for parent in target.parents:
        if parent == root:
            break
        try:
            parent.rmdir()
        except OSError:
            break
    return True
