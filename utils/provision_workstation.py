"""
Utilidad de linea de comandos para provisionar credenciales de un puesto de trabajo.

Permite registrar el workstation token en Windows Credential Manager sin necesidad
de escribirlo en config.local.json.

Uso:
  python -m utils.provision_workstation

El usuario no necesita volver a introducir las credenciales en cada arranque:
la aplicacion las recupera automaticamente de Windows Credential Manager.

NOTA: integrations_api_key y dgt_api_key son claves legacy eliminadas en v1.7.0.
El puesto autentica exclusivamente con WorkstationToken.
"""
from __future__ import annotations

import argparse
import getpass
import sys


def _solicitar_valor(prompt: str, nombre: str, actual: str | None) -> str | None:
    if actual:
        print(f"  [{nombre}] Ya hay un valor almacenado.")
        resp = input("  Reemplazar? (s/N): ").strip().lower()
        if resp != "s":
            return None
    valor = getpass.getpass(f"  {prompt}: ").strip()
    if not valor:
        print(f"  Valor vacio; '{nombre}' no se modifico.")
        return None
    return valor


def provisionar_workstation_token() -> None:
    from utils.credential_store import get_workstation_token, store_workstation_token
    print("\n--- Workstation Token ---")
    actual = get_workstation_token()
    token = _solicitar_valor("Workstation token (g2a3_wks_...)", "workstation_token", actual)
    if token is None:
        return
    ok = store_workstation_token(token)
    if ok:
        print("  Token almacenado en Windows Credential Manager.")
    else:
        print("  ERROR: keyring no disponible. Token no guardado.", file=sys.stderr)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Provisiona credenciales del puesto en Windows Credential Manager."
    )
    parser.parse_args()

    print("=== Provisionado de credenciales Gest2A3Eco ===")
    print("Las credenciales se guardan en Windows Credential Manager.")
    print("No se almacenan en ningun fichero de texto ni config.local.json.\n")

    provisionar_workstation_token()

    print("\nProvisionado completado.")


if __name__ == "__main__":
    main()
