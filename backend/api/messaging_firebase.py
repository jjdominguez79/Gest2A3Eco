from __future__ import annotations

import json
import logging
from datetime import timedelta
from pathlib import Path
from typing import NamedTuple

from backend.api.config import get_settings


LOG = logging.getLogger(__name__)
_APP = None


class FcmResult(NamedTuple):
    success: bool
    # True cuando el token es invalido de forma permanente y el dispositivo
    # debe desactivarse. False en errores transitorios (red, timeout, etc.).
    permanent_failure: bool


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


def send_fcm(push_token: str, payload: dict, *, platform: str = 'android') -> FcmResult:
    """Envia una notificacion FCM al token indicado.

    Devuelve un FcmResult con:
    - success: True si el envio tuvo exito.
    - permanent_failure: True si el token es invalido y el dispositivo debe
      desactivarse. False en errores transitorios (red, cuota, etc.).
    """
    app = _app()
    if app is None:
        return FcmResult(success=False, permanent_failure=False)
    try:
        from firebase_admin import messaging

        data = {
            str(k): str(v)
            for k, v in payload.items()
            if v is not None and str(v)
        }
        title = data.pop('title', 'Gestinem')
        body = data.pop('body', 'Tienes un nuevo mensaje')

        webpush = None
        if platform == 'web':
            web_app_url = get_settings().messaging_app_web_url
            conversation_id = data.get('conversation_id', '')
            thread_id = data.get('thread_id', '')
            document_id = data.get('document_id', '')
            if conversation_id:
                link = f'{web_app_url}/#/conversation/{conversation_id}'
            elif thread_id:
                link = f'{web_app_url}/#/internal/{thread_id}'
            elif document_id:
                link = f'{web_app_url}/#/documents/{document_id}'
            else:
                link = f'{web_app_url}/'
            webpush = messaging.WebpushConfig(
                notification=messaging.WebpushNotification(
                    title=title,
                    body=body,
                    icon='/icons/Icon-192.png',
                ),
                fcm_options=messaging.WebpushFCMOptions(link=link),
            )

        notification = messaging.Notification(title=title, body=body)
        android = None
        if platform == 'android':
            # Android usa una notificacion local controlada por Flutter. Asi
            # cada chat tiene un unico ID, se puede cancelar al leer y el tap
            # conserva siempre el destino exacto.
            data['title'] = title
            data['body'] = body
            target_id = data.get('target_id') or data.get('conversation_id') or data.get('thread_id')
            target_type = data.get('target_type', 'message')
            android = messaging.AndroidConfig(
                priority='high',
                ttl=timedelta(hours=24),
                collapse_key=(
                    f'{target_type}:{target_id}'
                    if target_id else 'gestinem:notifications'
                ),
            )
            notification = None

        messaging.send(
            messaging.Message(
                token=push_token,
                notification=notification,
                data=data,
                webpush=webpush,
                android=android,
            ),
            app=app,
        )
        return FcmResult(success=True, permanent_failure=False)
    except Exception as exc:
        permanent = _is_permanent_error(exc)
        # Solo el prefijo del token para no exponer el valor completo en logs.
        token_hint = push_token[:10] + '...' if len(push_token) > 10 else '???'
        if permanent:
            LOG.warning(
                'Token FCM invalido permanente (token=%s, platform=%s): %s',
                token_hint, platform, exc,
            )
        else:
            LOG.warning(
                'Error transitorio FCM (token=%s, platform=%s): %s',
                token_hint, platform, exc,
            )
        return FcmResult(success=False, permanent_failure=permanent)


def _is_permanent_error(exc: Exception) -> bool:
    """True si el error indica que el token ya no es valido."""
    try:
        from firebase_admin import messaging as _m
        if isinstance(exc, (_m.UnregisteredError, _m.SenderIdMismatchError)):
            return True
    except (ImportError, AttributeError):
        pass
    # Fallback por texto para entornos donde firebase_admin no esta disponible.
    msg = str(exc).lower()
    return any(
        kw in msg
        for kw in (
            'unregistered',
            'registration-token-not-registered',
            'invalid-registration-token',
            'not-registered',
            'mismatched-credential',
            'sender id mismatch',
        )
    )
