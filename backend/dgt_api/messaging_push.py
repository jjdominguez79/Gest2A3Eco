from __future__ import annotations

import json
import logging

from backend.dgt_api.config import get_settings


LOG = logging.getLogger(__name__)


def configured() -> bool:
    cfg = get_settings()
    return bool(cfg.messaging_vapid_public_key and cfg.messaging_vapid_private_key)


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
            timeout=20,
        )
        return True
    except WebPushException as exc:
        LOG.warning("No se pudo entregar una notificacion push: %s", exc)
        return False
