"""
Cifrado simetrico propio para contrasenas de certificados digitales.

Usa una clave de aplicacion fija combinada con un salt aleatorio por mensaje
para generar un keystream (modo contador sobre HMAC-SHA256) que se aplica
mediante XOR. No depende de librerias externas (no usa DPAPI ni la libreria
'cryptography'), por lo que el resultado es portatil entre los distintos
equipos del despacho que comparten la base de datos.

No es un cifrado de grado militar, pero evita guardar las contrasenas de los
certificados en texto plano dentro de la base de datos.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import os

_APP_KEY = b"Gest2A3Eco-Notificaciones-Electronicas-clave-app-2026"


def _keystream(salt: bytes, length: int) -> bytes:
    out = b""
    counter = 0
    while len(out) < length:
        out += hmac.new(_APP_KEY, salt + counter.to_bytes(4, "big"), hashlib.sha256).digest()
        counter += 1
    return out[:length]


def cifrar_password(texto_plano: str | None) -> str | None:
    """Cifra una cadena de texto. Devuelve None si la entrada es None o vacia."""
    if not texto_plano:
        return None
    datos = texto_plano.encode("utf-8")
    salt = os.urandom(8)
    ks = _keystream(salt, len(datos))
    cifrado = bytes(a ^ b for a, b in zip(datos, ks))
    return base64.urlsafe_b64encode(salt + cifrado).decode("ascii")


def descifrar_password(texto_cifrado: str | None) -> str | None:
    """Descifra una cadena previamente cifrada con cifrar_password."""
    if not texto_cifrado:
        return None
    try:
        crudo = base64.urlsafe_b64decode(texto_cifrado.encode("ascii"))
    except Exception:
        return None
    salt, cifrado = crudo[:8], crudo[8:]
    ks = _keystream(salt, len(cifrado))
    datos = bytes(a ^ b for a, b in zip(cifrado, ks))
    try:
        return datos.decode("utf-8")
    except UnicodeDecodeError:
        return None
