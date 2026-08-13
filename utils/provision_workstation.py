"""
Utilidad de linea de comandos para provisionar credenciales de un puesto de trabajo.

Permite registrar el workstation token y la clave de API de integraciones en
Windows Credential Manager sin necesidad de escribirlas en config.local.json.

Uso:
  python -m utils.provision_workstation
  python -m utils.provision_workstation --only-token
  python -m utils.provision_workstation --only-key

El usuario no necesita volver a introducir las credenciales en cada arranque:
la aplicacion las recupera automaticamente de Windows Credential Manager.
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


def provisionar_integrations_api_key() -> None:
    from utils.credential_store import get_integrations_api_key, store_integrations_api_key
    print("\n--- Integrations API Key ---")
    actual = get_integrations_api_key()
    key = _solicitar_valor("Clave de API del backend de integraciones", "integrations_api_key", actual)
    if key is None:
        return
    ok = store_integrations_api_key(key)
    if ok:
        print("  Clave almacenada en Windows Credential Manager.")
    else:
        print("  ERROR: keyring no disponible. Clave no guardada.", file=sys.stderr)


def provisionar_azure_doc_key() -> None:
    from utils.credential_store import get_azure_doc_key, store_azure_doc_key
    print("\n--- Azure Document Intelligence Key ---")
    actual = get_azure_doc_key()
    key = _solicitar_valor("Clave de Azure Document Intelligence", "azure_doc_intelligence_key", actual)
    if key is None:
        return
    ok = store_azure_doc_key(key)
    if ok:
        print("  Clave Azure almacenada en Windows Credential Manager.")
    else:
        print("  ERROR: keyring no disponible. Clave no guardada.", file=sys.stderr)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Provisiona credenciales del puesto en Windows Credential Manager."
    )
    parser.add_argument("--only-token", action="store_true", help="Solo provisionar workstation token.")
    parser.add_argument("--only-key", action="store_true", help="Solo provisionar integrations API key.")
    parser.add_argument("--only-azure", action="store_true", help="Solo provisionar clave Azure OCR.")
    args = parser.parse_args()

    print("=== Provisionado de credenciales Gest2A3Eco ===")
    print("Las credenciales se guardan en Windows Credential Manager.")
    print("No se almacenan en ningun fichero de texto ni config.local.json.\n")

    if args.only_token:
        provisionar_workstation_token()
    elif args.only_key:
        provisionar_integrations_api_key()
    elif args.only_azure:
        provisionar_azure_doc_key()
    else:
        provisionar_workstation_token()
        provisionar_integrations_api_key()
        provisionar_azure_doc_key()

    print("\nProvisionado completado.")


if __name__ == "__main__":
    main()
