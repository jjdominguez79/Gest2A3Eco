"""Convierte un certificado PKCS#12 (.p12/.pfx) a archivos PEM."""
from __future__ import annotations

import argparse
import getpass
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.serialization import pkcs12


def _ruta_disponible(ruta: Path, sobrescribir: bool) -> None:
    if ruta.exists() and not sobrescribir:
        raise FileExistsError(
            f"Ya existe '{ruta}'. Usa --sobrescribir si deseas reemplazarlo."
        )


def convertir(origen: Path, destino: Path, sobrescribir: bool = False) -> list[Path]:
    if not origen.is_file():
        raise FileNotFoundError(f"No existe el certificado: {origen}")
    if origen.suffix.lower() not in {".p12", ".pfx"}:
        raise ValueError("El archivo debe tener extension .p12 o .pfx.")

    password_p12 = getpass.getpass("Contrasena actual del P12/PFX: ")
    clave_pem_1 = getpass.getpass(
        "Nueva contrasena para proteger clave_privada.pem: "
    )
    if not clave_pem_1:
        raise ValueError("La clave privada PEM debe quedar protegida con contrasena.")
    clave_pem_2 = getpass.getpass("Repite la nueva contrasena: ")
    if clave_pem_1 != clave_pem_2:
        raise ValueError("Las nuevas contrasenas no coinciden.")

    try:
        privada, certificado, cadena = pkcs12.load_key_and_certificates(
            origen.read_bytes(),
            password_p12.encode("utf-8") if password_p12 else None,
        )
    except Exception as exc:
        raise ValueError(
            "No se pudo abrir el P12/PFX. Revisa la contrasena y el archivo."
        ) from exc

    if privada is None or certificado is None:
        raise ValueError("El P12/PFX no contiene certificado y clave privada.")

    destino.mkdir(parents=True, exist_ok=True)
    ruta_certificado = destino / "certificado.pem"
    ruta_privada = destino / "clave_privada.pem"
    ruta_cadena = destino / "cadena_certificacion.pem"
    for ruta in (ruta_certificado, ruta_privada, ruta_cadena):
        _ruta_disponible(ruta, sobrescribir)

    ruta_certificado.write_bytes(
        certificado.public_bytes(serialization.Encoding.PEM)
    )
    ruta_privada.write_bytes(
        privada.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.BestAvailableEncryption(
                clave_pem_1.encode("utf-8")
            ),
        )
    )

    generados = [ruta_certificado, ruta_privada]
    if cadena:
        ruta_cadena.write_bytes(
            b"".join(cert.public_bytes(serialization.Encoding.PEM) for cert in cadena)
        )
        generados.append(ruta_cadena)
    return generados


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Convierte un certificado P12/PFX a PEM sin usar OpenSSL."
    )
    parser.add_argument("certificado", type=Path, help="Ruta del archivo .p12 o .pfx")
    parser.add_argument(
        "--destino",
        type=Path,
        help="Carpeta de salida (por defecto: <nombre>_pem junto al certificado)",
    )
    parser.add_argument(
        "--sobrescribir",
        action="store_true",
        help="Permite reemplazar archivos PEM existentes",
    )
    args = parser.parse_args()

    origen = args.certificado.expanduser().resolve()
    destino = (
        args.destino.expanduser().resolve()
        if args.destino
        else origen.parent / f"{origen.stem}_pem"
    )
    try:
        generados = convertir(origen, destino, args.sobrescribir)
    except Exception as exc:
        parser.exit(1, f"ERROR: {exc}\n")

    print("Archivos generados:")
    for ruta in generados:
        print(f"  {ruta}")
    print("\nLa clave privada esta cifrada. No la compartas ni la subas a Git.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
