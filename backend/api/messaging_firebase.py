from __future__ import annotations

import logging
from pathlib import Path

from backend.api.config import get_settings


LOG = logging.getLogger(__name__)
_APP = None


def configured() -> bool:
    path = get_settings().messaging_firebase_credentials.strip()
    return bool(path and Path(path).is_file())


def _app():
    global _APP
    if _APP is not None:
        return _APP
    if not configured():
        return None
    import firebase_admin
    from firebase_admin import credentials

    try:
        _APP = firebase_admin.get_app("gestinem-messaging")
    except ValueError:
        _APP = firebase_admin.initialize_app(
            credentials.Certificate(get_settings().messaging_firebase_credentials),
            name="gestinem-messaging",
        )
    return _APP


def send_fcm(push_token: str, payload: dict) -> bool:
    app = _app()
    if app is None:
        return False
    try:
        from firebase_admin import messaging

        data = {str(key): str(value) for key, value in payload.items() if value is not None}
        messaging.send(
            messaging.Message(
                token=push_token,
                notification=messaging.Notification(
                    title=data.pop("title", "Gestinem"),
                    body=data.pop("body", "Tienes un nuevo mensaje"),
                ),
                data=data,
            ),
            app=app,
        )
        return True
    except Exception:
        LOG.exception("No se pudo entregar una notificacion FCM")
        return False
