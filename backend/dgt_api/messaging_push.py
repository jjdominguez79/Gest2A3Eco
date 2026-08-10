from __future__ import annotations

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


def send_push(subscription: dict, payload: dict) -> bool:
    if not configured():
        return False
    from pywebpush import WebPushException, webpush

    cfg = get_settings()
    try:
        webpush(
            subscription_info=subscription,
            data=json.dumps(payload, ensure_ascii=False),
            vapid_private_key=cfg.messaging_vapid_private_key,
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
