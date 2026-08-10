from __future__ import annotations

import base64
import json
import logging
from urllib.parse import urlparse

from backend.dgt_api.config import get_settings


LOG = logging.getLogger(__name__)


def configured() -> bool:
    cfg = get_settings()
    return bool(cfg.messaging_vapid_public_key and cfg.messaging_vapid_private_key)


def _headers_for_subscription(subscription: dict) -> dict[str, str]:
    """Cabeceras adicionales requeridas por Edge cuando usa WNS en Windows."""
    endpoint = str(subscription.get("endpoint") or "")
    hostname = (urlparse(endpoint).hostname or "").lower()
    if hostname.endswith(".notify.windows.com") or hostname == "notify.windows.com":
        return {
            "X-WNS-Type": "wns/raw",
            "Content-Type": "application/octet-stream",
        }
    return {}


def _normalize_private_key(private_key: str) -> str:
    """Convierte una clave VAPID Web Push de 32 bytes al DER que espera py_vapid."""
    value = private_key.strip()
    if not value or "-----BEGIN" in value:
        return value

    try:
        padding = "=" * (-len(value) % 4)
        raw_key = base64.urlsafe_b64decode(value + padding)
    except (ValueError, TypeError):
        return value

    # Las claves generadas por web-push (Node) son el escalar P-256 en Base64URL.
    # pywebpush/py_vapid, en cambio, espera una clave privada DER o PEM.
    if len(raw_key) != 32:
        return value

    try:
        from cryptography.hazmat.primitives import serialization
        from cryptography.hazmat.primitives.asymmetric import ec

        key = ec.derive_private_key(int.from_bytes(raw_key, "big"), ec.SECP256R1())
        der_key = key.private_bytes(
            encoding=serialization.Encoding.DER,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        )
    except (ValueError, TypeError):
        return value

    return base64.urlsafe_b64encode(der_key).rstrip(b"=").decode("ascii")


def send_push(subscription: dict, payload: dict) -> bool:
    if not configured():
        return False
    from pywebpush import WebPushException, webpush

    cfg = get_settings()
    try:
        webpush(
            subscription_info=subscription,
            data=json.dumps(payload, ensure_ascii=False),
            vapid_private_key=_normalize_private_key(cfg.messaging_vapid_private_key),
            vapid_claims={"sub": cfg.messaging_vapid_subject},
            headers=_headers_for_subscription(subscription),
            timeout=20,
        )
        return True
    except WebPushException as exc:
        LOG.warning("No se pudo entregar una notificacion push: %s", exc)
        return False
    except Exception:
        LOG.exception("Error inesperado al preparar una notificacion push")
        return False
