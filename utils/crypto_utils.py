"""
Cifrado simetrico para contrasenas de certificados digitales.

Objetivo de seguridad
---------------------
Las contrasenas de los certificados de los clientes NO deben quedar en texto
plano en la base de datos, y tampoco deben poder descifrarse solo con el codigo
fuente (el repositorio puede ser accesible). Por eso la clave de cifrado ya NO
esta incrustada en el codigo: se genera aleatoriamente la primera vez y se
guarda en un fichero local del despacho ("keyfile"), fuera del control de
versiones.

Formato de los datos cifrados
-----------------------------
- Formato nuevo (v2):  "v2:" + base64url( salt[16] + ciphertext + tag[32] )
    * keystream = HMAC-SHA256(key, salt || counter)  (modo contador)  -> XOR
    * tag       = HMAC-SHA256(key, salt || ciphertext)  (autenticacion)
    * key       = 32 bytes aleatorios almacenados en el keyfile
- Formato antiguo (legacy): base64url( salt[8] + ciphertext )
    * Se mantiene SOLO para poder descifrar contrasenas guardadas por versiones
      anteriores. Al reguardar el certificado se recifra en formato v2.

Portabilidad entre equipos del despacho
---------------------------------------
El keyfile se guarda junto a la base de datos (carpeta 'plantillas/'), que ya
se comparte entre los equipos del despacho. Copia el fichero '.notif_key' junto
con 'gest2a3eco.db' y las contrasenas seguiran descifrandose en todos los
equipos. Si el keyfile se pierde, las contrasenas v2 no se podran recuperar
(habra que volver a introducirlas): trata '.notif_key' como un secreto.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import os

# ---------------------------------------------------------------------------
# Clave legacy (solo lectura de datos antiguos). No usar para cifrar.
# ---------------------------------------------------------------------------
_LEGACY_APP_KEY = b"Gest2A3Eco-Notificaciones-Electronicas-clave-app-2026"

_V2_PREFIX = "v2:"
_KEY_LEN = 32

# Ruta del keyfile. Se resuelve de forma perezosa; se puede sobreescribir con
# configurar_keyfile() al arrancar la aplicacion.
_KEYFILE_PATH: str | None = None
_KEY_CACHE: bytes | None = None


def configurar_keyfile(path: str) -> None:
    """Fija la ruta del keyfile (llamar al arrancar la app si se desea)."""
    global _KEYFILE_PATH, _KEY_CACHE
    _KEYFILE_PATH = path
    _KEY_CACHE = None


def _default_keyfile_path() -> str:
    """Keyfile por defecto: <raiz_proyecto>/plantillas/.notif_key.

    crypto_utils.py vive en utils/, por lo que la raiz del proyecto es el
    directorio padre. Se usa 'plantillas/' porque es donde reside la base de
    datos y ya se comparte entre equipos.
    """
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(root, "plantillas", ".notif_key")


def _load_or_create_key() -> bytes:
    global _KEY_CACHE
    if _KEY_CACHE is not None:
        return _KEY_CACHE
    path = _KEYFILE_PATH or _default_keyfile_path()
    try:
        with open(path, "rb") as fh:
            raw = fh.read().strip()
        key = base64.urlsafe_b64decode(raw)
        if len(key) != _KEY_LEN:
            raise ValueError("longitud de clave invalida")
    except Exception:
        # Generar y persistir una clave nueva.
        key = os.urandom(_KEY_LEN)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "wb") as fh:
            fh.write(base64.urlsafe_b64encode(key))
        try:  # Permisos restrictivos donde el SO lo soporte.
            os.chmod(path, 0o600)
        except Exception:
            pass
    _KEY_CACHE = key
    return key


def _keystream(key: bytes, salt: bytes, length: int) -> bytes:
    out = b""
    counter = 0
    while len(out) < length:
        out += hmac.new(key, salt + counter.to_bytes(4, "big"), hashlib.sha256).digest()
        counter += 1
    return out[:length]


# ---------------------------------------------------------------------------
# API publica (compatible con la version anterior)
# ---------------------------------------------------------------------------

def cifrar_password(texto_plano: str | None) -> str | None:
    """Cifra una cadena (formato v2). Devuelve None si la entrada es vacia."""
    if not texto_plano:
        return None
    key = _load_or_create_key()
    datos = texto_plano.encode("utf-8")
    salt = os.urandom(16)
    ks = _keystream(key, salt, len(datos))
    cifrado = bytes(a ^ b for a, b in zip(datos, ks))
    tag = hmac.new(key, salt + cifrado, hashlib.sha256).digest()
    blob = base64.urlsafe_b64encode(salt + cifrado + tag).decode("ascii")
    return _V2_PREFIX + blob


def _descifrar_v2(texto_cifrado: str) -> str | None:
    key = _load_or_create_key()
    try:
        crudo = base64.urlsafe_b64decode(texto_cifrado[len(_V2_PREFIX):].encode("ascii"))
    except Exception:
        return None
    if len(crudo) < 16 + 32:
        return None
    salt, cifrado, tag = crudo[:16], crudo[16:-32], crudo[-32:]
    esperado = hmac.new(key, salt + cifrado, hashlib.sha256).digest()
    if not hmac.compare_digest(tag, esperado):
        return None  # clave incorrecta o dato manipulado
    ks = _keystream(key, salt, len(cifrado))
    datos = bytes(a ^ b for a, b in zip(cifrado, ks))
    try:
        return datos.decode("utf-8")
    except UnicodeDecodeError:
        return None


def _descifrar_legacy(texto_cifrado: str) -> str | None:
    try:
        crudo = base64.urlsafe_b64decode(texto_cifrado.encode("ascii"))
    except Exception:
        return None
    salt, cifrado = crudo[:8], crudo[8:]
    ks = _keystream(_LEGACY_APP_KEY, salt, len(cifrado))
    datos = bytes(a ^ b for a, b in zip(cifrado, ks))
    try:
        return datos.decode("utf-8")
    except UnicodeDecodeError:
        return None


def descifrar_password(texto_cifrado: str | None) -> str | None:
    """Descifra una cadena cifrada con cifrar_password (v2 o legacy)."""
    if not texto_cifrado:
        return None
    if texto_cifrado.startswith(_V2_PREFIX):
        return _descifrar_v2(texto_cifrado)
    return _descifrar_legacy(texto_cifrado)


def es_legacy(texto_cifrado: str | None) -> bool:
    """True si el valor esta en el formato antiguo (conviene recifrarlo)."""
    return bool(texto_cifrado) and not texto_cifrado.startswith(_V2_PREFIX)
