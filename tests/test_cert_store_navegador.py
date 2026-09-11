from datetime import datetime, timedelta, timezone

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives.serialization import pkcs12
from cryptography.x509.oid import NameOID

from services.aapp.cert_store import CertMaterial, preparar_pfx_para_navegador


def _crear_pfx(password: str) -> tuple[bytes, int]:
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "Cliente Piloto")])
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
    contenido = pkcs12.serialize_key_and_certificates(
        b"cliente-piloto",
        key,
        certificate,
        None,
        serialization.BestAvailableEncryption(password.encode("utf-8")),
    )
    return contenido, certificate.serial_number


def test_prepara_copia_moderna_sin_modificar_el_pfx_original(tmp_path):
    original, serial = _crear_pfx("clave-original")
    origen = tmp_path / "original.pfx"
    destino = tmp_path / "navegador.pfx"
    origen.write_bytes(original)
    material = CertMaterial(
        cert_id="central",
        nombre="Cliente Piloto",
        nif_titular=None,
        ruta_archivo=str(origen),
        password="clave-original",
    )

    ruta, password_temporal = preparar_pfx_para_navegador(material, str(destino))

    assert ruta == str(destino)
    assert password_temporal != "clave-original"
    assert origen.read_bytes() == original
    key, cert, _adicionales = pkcs12.load_key_and_certificates(
        destino.read_bytes(),
        password_temporal.encode("utf-8"),
    )
    assert key is not None
    assert cert.serial_number == serial
