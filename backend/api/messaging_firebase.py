from __future__ import annotations

import json
import logging
from pathlib import Path

from backend.api.config import get_settings


LOG = logging.getLogger(__name__)
_APP = None


def configured() -> bool:
    return _credential_source() is not None


def _credential_source() -> str | dict | None:
    settings = get_settings()
    path = settings.messaging_firebase_credentials.strip()
    if path and Path(path).is_file():
        return path
    raw = settings.messaging_firebase_credentials_json.strip()
    if not raw:
        return None
    try:
        value = json.loads(raw)
    except (TypeError, ValueError):
        return None
    required = {"type", "project_id", "private_key", "client_email"}
    return value if isinstance(value, dict) and required <= value.keys() else None


def _app():
    global _APP
    if _APP is not None:
        return _APP
    source = _credential_source()
    if source is None:
        return None
    import firebase_admin
    from firebase_admin import credentials

    try:
        _APP = firebase_admin.get_app("gestinem-messaging")
    except ValueError:
        _APP = firebase_admin.initialize_app(
            credentials.Certificate(source),
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
