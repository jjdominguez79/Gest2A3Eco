"""Custodia cifrada de certificados PFX usados por el worker AAPP."""

from __future__ import annotations

import base64
import hashlib
import json
import os
import re
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.serialization import pkcs12
from cryptography.x509.oid import NameOID

from backend.api.config import get_settings


MAX_PFX_BYTES = 2 * 1024 * 1024
_FORMAT_VERSION = b"G2A3CERT1"


@dataclass(frozen=True)
class CertificateMetadata:
    common_name: str
    tax_id: str
    issuer: str
    serial_number: str
    valid_from: datetime
    valid_until: datetime
    pfx_sha256: str


def _master_key() -> bytes:
    encoded = get_settings().client_certificates_master_key
    if not encoded:
        raise RuntimeError("CLIENT_CERTIFICATES_MASTER_KEY no esta configurada")
    try:
        padded = encoded + "=" * (-len(encoded) % 4)
        key = base64.urlsafe_b64decode(padded.encode("ascii"))
    except Exception as exc:
        raise RuntimeError("CLIENT_CERTIFICATES_MASTER_KEY no es base64 valida") from exc
    if len(key) != 32:
        raise RuntimeError("CLIENT_CERTIFICATES_MASTER_KEY debe contener 32 bytes")
    return key


def _as_utc(value: datetime) -> datetime:
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


def _first_name(name, oid: NameOID) -> str:
    attrs = name.get_attributes_for_oid(oid)
    return str(attrs[0].value) if attrs else ""


def inspect_pfx(content: bytes, password: str) -> CertificateMetadata:
    if not content:
        raise ValueError("El certificado esta vacio")
    if len(content) > MAX_PFX_BYTES:
        raise ValueError("El certificado supera el limite de 2 MB")
    try:
        _key, certificate, _chain = pkcs12.load_key_and_certificates(
            content,
            password.encode("utf-8") if password else None,
        )
    except Exception as exc:
        raise ValueError("No se pudo abrir el PFX; revisa la contrasena") from exc
    if certificate is None or _key is None:
        raise ValueError("El PFX no contiene certificado y clave privada")
    common_name = _first_name(certificate.subject, NameOID.COMMON_NAME)
    subject_serial = _first_name(certificate.subject, NameOID.SERIAL_NUMBER)
    subject_text = f"{certificate.subject.rfc4514_string()} {subject_serial}"
    tax_match = re.search(
        r"(?:NIF|CIF|IDCES)[-:= ]*([0-9A-Z-]{8,12})",
        subject_text,
        re.IGNORECASE,
    )
    tax_id = tax_match.group(1).upper().replace("-", "") if tax_match else ""
    not_before = getattr(certificate, "not_valid_before_utc", None) or certificate.not_valid_before
    not_after = getattr(certificate, "not_valid_after_utc", None) or certificate.not_valid_after
    return CertificateMetadata(
        common_name=common_name,
        tax_id=tax_id,
        issuer=_first_name(certificate.issuer, NameOID.COMMON_NAME),
        serial_number=format(certificate.serial_number, "X"),
        valid_from=_as_utc(not_before),
        valid_until=_as_utc(not_after),
        pfx_sha256=hashlib.sha256(content).hexdigest(),
    )


def encrypt_material(content: bytes, password: str, organization_id: str) -> bytes:
    payload = json.dumps({
        "pfx": base64.b64encode(content).decode("ascii"),
        "password": password,
    }, separators=(",", ":")).encode("utf-8")
    nonce = os.urandom(12)
    encrypted = AESGCM(_master_key()).encrypt(
        nonce, payload, organization_id.encode("utf-8"),
    )
    return _FORMAT_VERSION + nonce + encrypted


def decrypt_material(blob: bytes, organization_id: str) -> tuple[bytes, str]:
    if not blob.startswith(_FORMAT_VERSION) or len(blob) <= len(_FORMAT_VERSION) + 12:
        raise ValueError("Sobre de certificado no valido")
    offset = len(_FORMAT_VERSION)
    nonce = blob[offset:offset + 12]
    encrypted = blob[offset + 12:]
    try:
        payload = AESGCM(_master_key()).decrypt(
            nonce, encrypted, organization_id.encode("utf-8"),
        )
        decoded = json.loads(payload.decode("utf-8"))
        return base64.b64decode(decoded["pfx"]), str(decoded.get("password") or "")
    except Exception as exc:
        raise ValueError("No se pudo descifrar el certificado") from exc


class ClientCertificateVaultStorage:
    """Blob privado separado del area documental y siempre cifrado en origen."""

    def __init__(self) -> None:
        cfg = get_settings()
        self._connection_string = cfg.client_certificates_azure_connection_string
        self._container_name = cfg.client_certificates_azure_container
        self._local_dir = cfg.client_certificates_storage_dir
        self._container = None
        if self._connection_string:
            from azure.core.exceptions import ResourceExistsError
            from azure.storage.blob import BlobServiceClient
            service = BlobServiceClient.from_connection_string(self._connection_string)
            self._container = service.get_container_client(self._container_name)
            try:
                self._container.create_container()
            except ResourceExistsError:
                pass
        elif not cfg.client_certificates_allow_local_storage:
            raise RuntimeError(
                "CLIENT_CERTIFICATES_AZURE_CONNECTION_STRING es obligatoria; "
                "el almacenamiento local solo se permite en desarrollo"
            )

    def put(self, encrypted: bytes, organization_id: str) -> str:
        key = f"{organization_id}/{uuid.uuid4().hex}.g2cert"
        if self._container is not None:
            self._container.upload_blob(key, encrypted, overwrite=False)
        else:
            path = Path(self._local_dir).resolve() / key
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(encrypted)
        return key

    def get(self, key: str) -> bytes:
        if self._container is not None:
            return self._container.download_blob(key).readall()
        root = Path(self._local_dir).resolve()
        path = (root / key).resolve()
        if root not in path.parents or not path.is_file():
            raise ValueError("Ruta de certificado no valida")
        return path.read_bytes()

    def delete(self, key: str) -> None:
        if not key:
            return
        if self._container is not None:
            self._container.delete_blob(key, delete_snapshots="include")
            return
        root = Path(self._local_dir).resolve()
        path = (root / key).resolve()
        if root not in path.parents:
            raise ValueError("Ruta de certificado no valida")
        path.unlink(missing_ok=True)


def validate_vault_configuration() -> None:
    """Falla al arrancar si se habilita el modulo sin custodia segura."""
    _master_key()
    ClientCertificateVaultStorage()
