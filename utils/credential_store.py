"""
Almacenamiento seguro de credenciales en Windows Credential Manager.

Utiliza la libreria 'keyring' que delega en el proveedor nativo del sistema
operativo (Windows Credential Manager en Windows, Keychain en macOS, etc.).

Servicios registrados:
  - Gest2A3Eco/PostgreSQL          usuario:password de la base de datos
  - Gest2A3Eco/WorkstationToken    token de autenticacion del puesto
  - Gest2A3Eco/IntegrationsApiKey  clave de API del backend de integraciones
  - Gest2A3Eco/AzureDocIntelligence clave de Azure Document Intelligence
  - Gest2A3Eco/AzureStorage        cadena de conexion Azure Storage
  - Gest2A3Eco/MessagingApiKey     clave de API de mensajeria
  - Gest2A3Eco/MessagingDevice     token de dispositivo de mensajeria
  - Gest2A3Eco/AdminPassword       contrasena de administrador inicial
  - Gest2A3Eco/DesmarcarGeneradas  contrasena para desmarcar facturas generadas

Uso tipico:
  store_postgres_credentials("gest2a3eco", "secreto")
  user, pwd = get_postgres_credentials() or ("", "")

  store_workstation_token("g2a3_wks_...")
  token = get_workstation_token()
"""
from __future__ import annotations

import logging
import re

logger = logging.getLogger(__name__)

SERVICE_POSTGRES = "Gest2A3Eco/PostgreSQL"
USERNAME_POSTGRES = "db_user"

SERVICE_WORKSTATION = "Gest2A3Eco/WorkstationToken"
USERNAME_WORKSTATION = "workstation"

SERVICE_INTEGRATIONS_KEY = "Gest2A3Eco/IntegrationsApiKey"
USERNAME_INTEGRATIONS_KEY = "api_key"

SERVICE_AZURE_DOC_KEY = "Gest2A3Eco/AzureDocIntelligence"
USERNAME_AZURE_DOC_KEY = "azure_key"

SERVICE_AZURE_STORAGE = "Gest2A3Eco/AzureStorage"
USERNAME_AZURE_STORAGE = "connection_string"

SERVICE_MESSAGING_KEY = "Gest2A3Eco/MessagingApiKey"
USERNAME_MESSAGING_KEY = "api_key"

SERVICE_MESSAGING_DEVICE = "Gest2A3Eco/MessagingDevice"
USERNAME_MESSAGING_DEVICE = "device_token"

SERVICE_ADMIN_PWD = "Gest2A3Eco/AdminPassword"
USERNAME_ADMIN_PWD = "admin"

SERVICE_DESMARCAR = "Gest2A3Eco/DesmarcarGeneradas"
USERNAME_DESMARCAR = "desmarcar"


def _keyring_available() -> bool:
    try:
        import keyring  # noqa: F401
        return True
    except ImportError:
        return False


# ── Helpers genericos (privados) ──────────────────────────────────────────────

def _store_single(service: str, username: str, value: str) -> bool:
    """Guarda un valor unico en el almacen seguro. Devuelve True si OK."""
    if not _keyring_available():
        logger.warning("keyring no disponible; no se puede guardar '%s'.", service)
        return False
    import keyring
    keyring.set_password(service, username, value)
    logger.debug("Credencial guardada en Windows Credential Manager: %s.", service)
    return True


def _get_single(service: str, username: str) -> str | None:
    """Recupera un valor unico del almacen. Devuelve None si no existe o keyring no disponible."""
    if not _keyring_available():
        return None
    import keyring
    return keyring.get_password(service, username) or None


def _delete_single(service: str, username: str) -> None:
    """Elimina una entrada del almacen seguro, ignorando errores."""
    if not _keyring_available():
        return
    import keyring
    try:
        keyring.delete_password(service, username)
    except Exception:
        pass


def store_postgres_credentials(username: str, password: str) -> bool:
    """
    Guarda usuario y password de PostgreSQL en el almacen seguro.
    Devuelve True si se guardo correctamente, False si keyring no esta disponible.
    El username se guarda como metadata junto al password.
    """
    if not _keyring_available():
        logger.warning("keyring no disponible; credenciales PostgreSQL no se pueden guardar en el almacen seguro.")
        return False
    import keyring
    # Guardar como "usuario:password" para recuperar ambos
    keyring.set_password(SERVICE_POSTGRES, USERNAME_POSTGRES, f"{username}:{password}")
    logger.debug("Credenciales PostgreSQL guardadas en Windows Credential Manager.")
    return True


def get_postgres_credentials() -> tuple[str, str] | None:
    """
    Recupera (usuario, password) de PostgreSQL desde el almacen seguro.
    Devuelve None si no hay credenciales guardadas o keyring no esta disponible.
    """
    if not _keyring_available():
        return None
    import keyring
    value = keyring.get_password(SERVICE_POSTGRES, USERNAME_POSTGRES)
    if not value:
        return None
    if ":" in value:
        user, pwd = value.split(":", 1)
        return user, pwd
    return "", value


def delete_postgres_credentials() -> None:
    """Elimina las credenciales de PostgreSQL del almacen seguro."""
    if not _keyring_available():
        return
    import keyring
    try:
        keyring.delete_password(SERVICE_POSTGRES, USERNAME_POSTGRES)
    except Exception:
        pass


def _parse_dsn_manual(dsn: str) -> dict | None:
    """
    Parsea un DSN PostgreSQL de forma manual dividiendo por el ULTIMO '@'.

    Soporta contrasenas que contienen '@' sin URL-encodear, lo que hace que
    los parsers estandar (psycopg, regex con [^@]) fallen al dividir por el
    primer '@' en lugar del ultimo.

    Ejemplos validos:
      postgresql://user:p@ss@host:5433/db  -> password='p@ss', host='host'
      postgresql://user:pass@192.168.0.18:5432/db
    """
    # Eliminar el esquema
    stripped = re.sub(r'^postgres(?:ql)?://', '', dsn.strip())
    if not stripped:
        return None

    # Dividir credenciales y host por el ULTIMO '@'
    at_pos = stripped.rfind('@')
    if at_pos == -1:
        return None

    creds_str = stripped[:at_pos]
    host_str = stripped[at_pos + 1:]

    # Parsear user:password (la password puede contener ':' tambien, pero
    # el user no puede, asi que dividimos por el PRIMER ':')
    if ':' in creds_str:
        user, password = creds_str.split(':', 1)
    else:
        user, password = creds_str, ''

    # Parsear host:port/dbname
    m = re.match(r'(?P<host>[^:/]+)(?::(?P<port>\d+))?/(?P<dbname>[^?]+)', host_str)
    if not m:
        return None

    return {
        "user": user,
        "password": password,
        "host": m.group("host"),
        "port": int(m.group("port") or 5432),
        "dbname": m.group("dbname"),
    }


def migrate_from_dsn(dsn: str) -> dict:
    """
    Extrae credenciales del DSN, las guarda en el almacen seguro y devuelve
    la configuracion no sensible (host, port, database, user sin password).

    Entrada: postgres_dsn completo con password embebido, p.ej.:
      postgresql://usuario:password@192.168.0.18:5433/gest2a3eco

    Salida: dict con claves:
      database_engine, postgres_host, postgres_port, postgres_database, postgres_user
      (sin postgres_password)

    Si no se puede parsear el DSN, devuelve un dict vacio.
    No muestra la password en logs bajo ningun concepto.

    Nota: soporta contrasenas que contienen el caracter '@' sin escapar,
    usando el ultimo '@' del DSN como separador credentials/host.
    """
    dsn_clean = dsn.strip()
    try:
        from psycopg.conninfo import conninfo_to_dict
        params = conninfo_to_dict(dsn_clean)
        # psycopg puede devolver el host malformado si la password tiene '@' sin
        # URL-encodear. Detectarlo comprobando que el host no contenga '@'.
        if "@" in str(params.get("host") or ""):
            raise ValueError("Host malformado (contiene '@'); probablemente password con '@' sin escapar.")
    except Exception:
        # Fallback manual: dividir por el ULTIMO '@' para soportar passwords con '@'
        params = _parse_dsn_manual(dsn_clean)
        if not params:
            logger.warning("No se pudo parsear el DSN para migracion de credenciales.")
            return {}

    user = str(params.get("user") or "")
    password = str(params.get("password") or "")
    host = str(params.get("host") or "")
    port = int(params.get("port") or 5432)
    database = str(params.get("dbname") or "")

    if password:
        ok = store_postgres_credentials(user, password)
        if ok:
            logger.info(
                "Credenciales PostgreSQL migradas a Windows Credential Manager "
                "(usuario='%s', servidor='%s:%s').", user, host, port
            )
        else:
            logger.warning(
                "No se pudo migrar la password de PostgreSQL al almacen seguro. "
                "El DSN con password se conserva en config local."
            )
            return {}
    else:
        logger.debug("DSN sin password; no hay nada que migrar.")

    return {
        "database_engine": "postgres",
        "postgres_host": host,
        "postgres_port": port,
        "postgres_database": database,
        "postgres_user": user,
    }


# ── Workstation token ─────────────────────────────────────────────────────────

def store_workstation_token(token: str) -> bool:
    """Guarda el token de estacion de trabajo en el almacen seguro."""
    return _store_single(SERVICE_WORKSTATION, USERNAME_WORKSTATION, token)


def get_workstation_token() -> str | None:
    """Recupera el token de estacion de trabajo del almacen seguro."""
    return _get_single(SERVICE_WORKSTATION, USERNAME_WORKSTATION)


def delete_workstation_token() -> None:
    """Elimina el token de estacion de trabajo del almacen seguro."""
    _delete_single(SERVICE_WORKSTATION, USERNAME_WORKSTATION)


# ── Integrations API key ──────────────────────────────────────────────────────

def store_integrations_api_key(key: str) -> bool:
    """Guarda la clave de API del backend de integraciones."""
    return _store_single(SERVICE_INTEGRATIONS_KEY, USERNAME_INTEGRATIONS_KEY, key)


def get_integrations_api_key() -> str | None:
    """Recupera la clave de API del backend de integraciones."""
    return _get_single(SERVICE_INTEGRATIONS_KEY, USERNAME_INTEGRATIONS_KEY)


def delete_integrations_api_key() -> None:
    """Elimina la clave de API del backend de integraciones."""
    _delete_single(SERVICE_INTEGRATIONS_KEY, USERNAME_INTEGRATIONS_KEY)


# ── Azure Document Intelligence key ──────────────────────────────────────────

def store_azure_doc_key(key: str) -> bool:
    """Guarda la clave de Azure Document Intelligence."""
    return _store_single(SERVICE_AZURE_DOC_KEY, USERNAME_AZURE_DOC_KEY, key)


def get_azure_doc_key() -> str | None:
    """Recupera la clave de Azure Document Intelligence."""
    return _get_single(SERVICE_AZURE_DOC_KEY, USERNAME_AZURE_DOC_KEY)


def delete_azure_doc_key() -> None:
    """Elimina la clave de Azure Document Intelligence."""
    _delete_single(SERVICE_AZURE_DOC_KEY, USERNAME_AZURE_DOC_KEY)


# ── Azure Storage connection string ──────────────────────────────────────────

def store_azure_storage_conn(conn: str) -> bool:
    """Guarda la cadena de conexion de Azure Storage."""
    return _store_single(SERVICE_AZURE_STORAGE, USERNAME_AZURE_STORAGE, conn)


def get_azure_storage_conn() -> str | None:
    """Recupera la cadena de conexion de Azure Storage."""
    return _get_single(SERVICE_AZURE_STORAGE, USERNAME_AZURE_STORAGE)


def delete_azure_storage_conn() -> None:
    """Elimina la cadena de conexion de Azure Storage."""
    _delete_single(SERVICE_AZURE_STORAGE, USERNAME_AZURE_STORAGE)


# ── Messaging API key ─────────────────────────────────────────────────────────

def store_messaging_api_key(key: str) -> bool:
    """Guarda la clave de API de mensajeria."""
    return _store_single(SERVICE_MESSAGING_KEY, USERNAME_MESSAGING_KEY, key)


def get_messaging_api_key() -> str | None:
    """Recupera la clave de API de mensajeria."""
    return _get_single(SERVICE_MESSAGING_KEY, USERNAME_MESSAGING_KEY)


def delete_messaging_api_key() -> None:
    """Elimina la clave de API de mensajeria."""
    _delete_single(SERVICE_MESSAGING_KEY, USERNAME_MESSAGING_KEY)


# ── Messaging device token ────────────────────────────────────────────────────

def store_messaging_device_token(token: str) -> bool:
    """Guarda el token de dispositivo de mensajeria."""
    return _store_single(SERVICE_MESSAGING_DEVICE, USERNAME_MESSAGING_DEVICE, token)


def get_messaging_device_token() -> str | None:
    """Recupera el token de dispositivo de mensajeria."""
    return _get_single(SERVICE_MESSAGING_DEVICE, USERNAME_MESSAGING_DEVICE)


def delete_messaging_device_token() -> None:
    """Elimina el token de dispositivo de mensajeria."""
    _delete_single(SERVICE_MESSAGING_DEVICE, USERNAME_MESSAGING_DEVICE)


# ── Admin password ────────────────────────────────────────────────────────────

def store_admin_password(pwd: str) -> bool:
    """Guarda la contrasena de administrador inicial."""
    return _store_single(SERVICE_ADMIN_PWD, USERNAME_ADMIN_PWD, pwd)


def get_admin_password() -> str | None:
    """Recupera la contrasena de administrador inicial."""
    return _get_single(SERVICE_ADMIN_PWD, USERNAME_ADMIN_PWD)


def delete_admin_password() -> None:
    """Elimina la contrasena de administrador inicial."""
    _delete_single(SERVICE_ADMIN_PWD, USERNAME_ADMIN_PWD)


# ── Desmarcar generadas password ──────────────────────────────────────────────

def store_desmarcar_password(pwd: str) -> bool:
    """Guarda la contrasena para desmarcar facturas generadas."""
    return _store_single(SERVICE_DESMARCAR, USERNAME_DESMARCAR, pwd)


def get_desmarcar_password() -> str | None:
    """Recupera la contrasena para desmarcar facturas generadas."""
    return _get_single(SERVICE_DESMARCAR, USERNAME_DESMARCAR)


def delete_desmarcar_password() -> None:
    """Elimina la contrasena para desmarcar facturas generadas."""
    _delete_single(SERVICE_DESMARCAR, USERNAME_DESMARCAR)


# ── PostgreSQL (funciones heredadas con logica compuesta) ─────────────────────

def build_dsn_from_store(host: str, port: int | str, database: str, user: str = "") -> str | None:
    """
    Construye un DSN completo recuperando la password del almacen seguro.

    Si el almacen no tiene credenciales, devuelve None (la app debe pedir
    los datos al usuario).
    """
    creds = get_postgres_credentials()
    if not creds:
        return None
    stored_user, password = creds
    effective_user = user or stored_user
    try:
        from psycopg.conninfo import make_conninfo
        return make_conninfo(
            host=str(host or ""),
            port=int(port or 5432),
            dbname=str(database or ""),
            user=effective_user,
            password=password,
            connect_timeout=5,
        )
    except Exception as exc:
        logger.error("Error construyendo DSN desde almacen seguro: %s", exc)
        return None
