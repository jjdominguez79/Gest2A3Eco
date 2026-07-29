"""Exporta exclusivamente la parte publica de un certificado PKCS#12."""
from __future__ import annotations

import argparse
import getpass
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.serialization import pkcs12


def exportar(origen: Path, destino: Path) -> None:
    if not origen.is_file():
        raise FileNotFoundError(f"No existe el certificado: {origen}")
    if destino.exists():
        raise FileExistsError(f"Ya existe el archivo de destino: {destino}")

    password = getpass.getpass("Contrasena del certificado P12/PFX: ")
    try:
        _privada, certificado, _cadena = pkcs12.load_key_and_certificates(
            origen.read_bytes(),
            password.encode("utf-8") if password else None,
        )
    except Exception as exc:
        raise ValueError(
            "No se pudo abrir el certificado. Revisa la contrasena."
        ) from exc

    if certificado is None:
        raise ValueError("El archivo no contiene un certificado publico.")

    destino.write_bytes(certificado.public_bytes(serialization.Encoding.DER))
    print(f"\nCertificado publico generado:\n{destino}")
    print("\nEste archivo .cer no contiene la clave privada.")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Exporta la parte publica .cer de un archivo P12/PFX."
    )
    parser.add_argument("origen", type=Path)
    parser.add_argument("destino", type=Path)
    args = parser.parse_args()

    try:
        exportar(args.origen.expanduser().resolve(), args.destino.expanduser().resolve())
    except Exception as exc:
        parser.exit(1, f"ERROR: {exc}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
