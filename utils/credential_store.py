"""
Almacenamiento seguro de credenciales en Windows Credential Manager.

Utiliza la libreria 'keyring' que delega en el proveedor nativo del sistema
operativo (Windows Credential Manager en Windows, Keychain en macOS, etc.).

Las credenciales de PostgreSQL se almacenan con:
  - SERVICE_POSTGRES: clave de servicio para el par usuario/password de BD
  - USERNAME_POSTGRES: nombre de usuario fijo para la entrada del almacen

Uso tipico:
  store_postgres_credentials("gest2a3eco", "secreto")
  user, pwd = get_postgres_credentials() or ("", "")
"""
from __future__ import annotations

import logging
import re

logger = logging.getLogger(__name__)

SERVICE_POSTGRES = "Gest2A3Eco/PostgreSQL"
USERNAME_POSTGRES = "db_user"

SERVICE_DESMARCAR = "Gest2A3Eco/DesmarcarGeneradas"
USERNAME_DESMARCAR = "desmarcar"


def _keyring_available() -> bool:
    try:
        import keyring  # noqa: F401
        return True
    except ImportError:
        return False


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
    """
    try:
        from psycopg.conninfo import conninfo_to_dict
        params = conninfo_to_dict(dsn)
    except Exception:
        # Fallback: parsear con regex si psycopg no esta disponible
        pattern = re.compile(
            r"(?:postgres(?:ql)?://)"
            r"(?P<user>[^:@/]+)"
            r"(?::(?P<password>[^@]+))?"
            r"@(?P<host>[^:/]+)"
            r"(?::(?P<port>\d+))?"
            r"/(?P<dbname>[^?]+)"
        )
        m = pattern.match(dsn.strip())
        if not m:
            logger.warning("No se pudo parsear el DSN para migracion de credenciales.")
            return {}
        params = {
            "user": m.group("user") or "",
            "password": m.group("password") or "",
            "host": m.group("host") or "",
            "port": int(m.group("port") or 5432),
            "dbname": m.group("dbname") or "",
        }

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
