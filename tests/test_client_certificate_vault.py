from __future__ import annotations

import base64
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives.serialization import pkcs12
from cryptography.x509.oid import NameOID

from backend.api import client_certificate_vault as vault


def _pfx(password: str = "clave") -> bytes:
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    name = x509.Name([
        x509.NameAttribute(NameOID.COMMON_NAME, "Cliente Piloto"),
        x509.NameAttribute(NameOID.SERIAL_NUMBER, "IDCES-B12345678"),
    ])
    certificate = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(name)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(datetime.now(timezone.utc) - timedelta(days=1))
        .not_valid_after(datetime.now(timezone.utc) + timedelta(days=365))
        .sign(key, hashes.SHA256())
    )
    return pkcs12.serialize_key_and_certificates(
        b"cliente-piloto",
        key,
        certificate,
        None,
        serialization.BestAvailableEncryption(password.encode()),
    )


@pytest.fixture
def master_key(monkeypatch):
    encoded = base64.urlsafe_b64encode(b"k" * 32).decode("ascii")
    monkeypatch.setattr(
        vault,
        "get_settings",
        lambda: SimpleNamespace(client_certificates_master_key=encoded),
    )


def test_inspecta_pfx_y_extrae_nif():
    metadata = vault.inspect_pfx(_pfx(), "clave")

    assert metadata.common_name == "Cliente Piloto"
    assert metadata.tax_id == "B12345678"
    assert len(metadata.pfx_sha256) == 64
    assert metadata.valid_until > datetime.now(timezone.utc)


def test_sobre_cifrado_solo_abre_para_la_misma_empresa(master_key):
    original = _pfx()
    encrypted = vault.encrypt_material(original, "clave", "org-1")

    restored, password = vault.decrypt_material(encrypted, "org-1")

    assert restored == original
    assert password == "clave"
    assert b"clave" not in encrypted
    with pytest.raises(ValueError, match="descifrar"):
        vault.decrypt_material(encrypted, "org-2")


def test_rechaza_clave_maestra_con_longitud_incorrecta(monkeypatch):
    monkeypatch.setattr(
        vault,
        "get_settings",
        lambda: SimpleNamespace(
            client_certificates_master_key=base64.urlsafe_b64encode(b"corta").decode(),
        ),
    )

    with pytest.raises(RuntimeError, match="32 bytes"):
        vault.encrypt_material(b"pfx", "clave", "org-1")
