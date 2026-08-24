"""Tests para backend/api/messaging_firebase.py y la integracion FCM en messaging_api."""
from __future__ import annotations

import os
import uuid
from contextlib import contextmanager
from unittest.mock import MagicMock, patch

import pytest

os.environ.setdefault("DGT_DATABASE_URL", "sqlite:///")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

@contextmanager
def _patch_messaging(fake_messaging):
    """Parcha firebase_admin.messaging con un fake.

    Funciona tanto si firebase-admin esta instalado como si no lo esta.
    'from firebase_admin import messaging' dentro de send_fcm devuelve el fake.
    """
    try:
        import firebase_admin as _fb
        # Instalado: parcheamos el atributo del modulo real.
        with patch.object(_fb, 'messaging', fake_messaging):
            yield
    except ModuleNotFoundError:
        # No instalado: inyectamos un modulo fake en sys.modules.
        import sys
        import types
        fake_fb = types.ModuleType('firebase_admin')
        fake_fb.messaging = fake_messaging
        with patch.dict(sys.modules, {
            'firebase_admin': fake_fb,
            'firebase_admin.messaging': fake_messaging,
        }):
            yield


# ---------------------------------------------------------------------------
# Tests unitarios de messaging_firebase (sin dependencia de DB)
# ---------------------------------------------------------------------------

class TestSendFcm:
    def _module(self):
        import importlib
        from backend.api import messaging_firebase
        importlib.reload(messaging_firebase)
        return messaging_firebase

    def _fake_messaging(self, **overrides):
        m = MagicMock()
        m.Message = MagicMock(return_value=MagicMock())
        m.Notification = MagicMock(return_value=MagicMock())
        m.WebpushConfig = MagicMock(return_value=MagicMock())
        m.WebpushNotification = MagicMock(return_value=MagicMock())
        m.WebpushFCMOptions = MagicMock(return_value=MagicMock())
        m.UnregisteredError = type('UnregisteredError', (Exception,), {})
        m.SenderIdMismatchError = type('SenderIdMismatchError', (Exception,), {})
        for k, v in overrides.items():
            setattr(m, k, v)
        return m

    def test_retorna_false_cuando_no_configurado(self):
        mod = self._module()
        with patch.object(mod, '_app', return_value=None):
            result = mod.send_fcm('token-abc', {'title': 'T', 'body': 'B'})
        assert result.success is False
        assert result.permanent_failure is False

    def test_envio_exitoso_devuelve_success(self):
        mod = self._module()
        fake_messaging = self._fake_messaging()

        with patch.object(mod, '_app', return_value=MagicMock()):
            with _patch_messaging(fake_messaging):
                result = mod.send_fcm('token-android', {'title': 'Hola', 'body': 'Mundo'})

        assert result.success is True
        assert result.permanent_failure is False

    def test_web_incluye_webpush_config(self):
        mod = self._module()

        captured_link = {}

        def fake_fcm_options(link):
            captured_link['link'] = link
            return MagicMock()

        fake_messaging = self._fake_messaging(
            WebpushFCMOptions=fake_fcm_options,
        )

        with patch.object(mod, '_app', return_value=MagicMock()):
            with _patch_messaging(fake_messaging):
                result = mod.send_fcm(
                    'token-web',
                    {'title': 'T', 'body': 'B', 'conversation_id': 'conv-42'},
                    platform='web',
                )

        assert result.success is True
        fake_messaging.WebpushConfig.assert_called_once()
        assert 'conv-42' in captured_link.get('link', '')

    def test_android_no_incluye_webpush(self):
        mod = self._module()
        fake_messaging = self._fake_messaging()

        with patch.object(mod, '_app', return_value=MagicMock()):
            with _patch_messaging(fake_messaging):
                mod.send_fcm('token-and', {'title': 'T', 'body': 'B'}, platform='android')

        fake_messaging.WebpushConfig.assert_not_called()

    def test_enlace_chat_interno_usa_ruta_internal(self):
        mod = self._module()
        captured_link = {}

        def fake_fcm_options(link):
            captured_link['link'] = link
            return MagicMock()

        fake_messaging = self._fake_messaging(WebpushFCMOptions=fake_fcm_options)

        with patch.object(mod, '_app', return_value=MagicMock()):
            with _patch_messaging(fake_messaging):
                mod.send_fcm(
                    'token-web',
                    {'title': 'T', 'body': 'B', 'thread_id': 'thread-99'},
                    platform='web',
                )

        assert '/internal/thread-99' in captured_link.get('link', '')

    def test_error_unregistered_es_permanente(self):
        mod = self._module()

        class FakeUnregistered(Exception):
            pass

        fake_messaging = self._fake_messaging(
            send=MagicMock(side_effect=FakeUnregistered('unregistered')),
            UnregisteredError=FakeUnregistered,
        )

        with patch.object(mod, '_app', return_value=MagicMock()):
            with _patch_messaging(fake_messaging):
                with patch.object(mod, '_is_permanent_error', return_value=True):
                    result = mod.send_fcm('bad-token', {'title': 'T', 'body': 'B'})

        assert result.success is False
        assert result.permanent_failure is True

    def test_error_transitorio_no_es_permanente(self):
        mod = self._module()
        fake_messaging = self._fake_messaging(
            send=MagicMock(side_effect=ConnectionError('timeout')),
        )

        with patch.object(mod, '_app', return_value=MagicMock()):
            with _patch_messaging(fake_messaging):
                result = mod.send_fcm('token-ok', {'title': 'T', 'body': 'B'})

        assert result.success is False
        assert result.permanent_failure is False

    def test_log_no_expone_token_completo(self, caplog):
        import logging
        mod = self._module()
        long_token = 'x' * 80
        fake_messaging = self._fake_messaging(
            send=MagicMock(side_effect=Exception('bad')),
        )

        with caplog.at_level(logging.WARNING, logger='backend.api.messaging_firebase'):
            with patch.object(mod, '_app', return_value=MagicMock()):
                with _patch_messaging(fake_messaging):
                    mod.send_fcm(long_token, {'title': 'T', 'body': 'B'})

        for record in caplog.records:
            assert long_token not in record.getMessage()


class TestIsPermanentError:
    def _fn(self):
        from backend.api.messaging_firebase import _is_permanent_error
        return _is_permanent_error

    def test_unregistered_en_mensaje(self):
        assert self._fn()(Exception('registration-token-not-registered')) is True

    def test_not_registered_en_mensaje(self):
        assert self._fn()(Exception('not-registered')) is True

    def test_invalid_registration_token(self):
        assert self._fn()(Exception('invalid-registration-token')) is True

    def test_timeout_no_es_permanente(self):
        assert self._fn()(Exception('connection timed out')) is False

    def test_server_unavailable_no_es_permanente(self):
        assert self._fn()(Exception('server-unavailable')) is False


# ---------------------------------------------------------------------------
# Tests de integracion: dispositivos web, WebpushConfig y desactivacion
# ---------------------------------------------------------------------------

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

_engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})


@pytest.fixture(scope="module")
def db_tables():
    import sys, types
    from sqlalchemy.orm import DeclarativeBase

    class _Base(DeclarativeBase):
        pass

    if "backend.api.database" not in sys.modules:
        fake_db = types.ModuleType("backend.api.database")
        fake_db.Base = _Base
        fake_db.engine = _engine
        fake_db.SessionLocal = sessionmaker(bind=_engine)
        fake_db.build_engine = lambda url=None: _engine
        sys.modules["backend.api.database"] = fake_db

    from backend.api.database import Base
    import backend.api.messaging_models  # noqa: F401
    Base.metadata.create_all(_engine)
    return Base.metadata


@pytest.fixture
def db(db_tables):
    Session = sessionmaker(bind=_engine, autoflush=False)
    session = Session()
    try:
        yield session
    finally:
        session.rollback()
        session.close()


class TestRegistroDispositivoWeb:
    def test_alta_dispositivo_web(self, db):
        from backend.api.messaging_models import MessagingAppDevice
        suffix = uuid.uuid4().hex[:8]
        device = MessagingAppDevice(
            user_type="staff",
            user_id=f"staff-{suffix}",
            platform="web",
            push_token=f"web-token-{suffix}",
            active=True,
        )
        db.add(device)
        db.flush()
        assert device.platform == "web"
        assert device.active is True

    def test_push_interno_web_incluye_thread_id(self, db):
        from backend.api import messaging_api
        from backend.api.messaging_models import (
            MessagingAppDevice, MessagingStaff, MessagingStaffChannel,
            MessagingStaffThread,
        )

        suffix = uuid.uuid4().hex[:8]
        admin = MessagingStaff(
            external_id=f"admin-web-{suffix}", name="Admin",
            email=f"admin-web-{suffix}@gestinem.es", role="admin", active=True,
        )
        member = MessagingStaff(
            external_id=f"member-web-{suffix}", name="Ana",
            email=f"member-web-{suffix}@gestinem.es", role="empleado", active=True,
        )
        db.add_all([admin, member])
        db.flush()
        db.add(MessagingStaffChannel(
            staff_external_id=member.external_id, channel="fiscal",
        ))
        thread = MessagingStaffThread(
            key=f"group:fiscal:{suffix}", kind="group", channel="fiscal",
        )
        db.add(thread)
        db.flush()
        device = MessagingAppDevice(
            user_type="staff", user_id=member.external_id, platform="web",
            push_token=f"web-token-{suffix}-" + "y" * 20, active=True,
        )
        db.add(device)
        db.flush()

        background = MagicMock()
        with patch.object(messaging_api, "fcm_configured", return_value=True):
            messaging_api._queue_internal_pushes(db, background, thread, admin)

        background.add_task.assert_called_once()
        args = background.add_task.call_args.args
        assert args[0] is messaging_api._send_push_and_handle
        assert args[1] == device.push_token    # push_token
        assert args[3] == device.platform       # platform = 'web'
        assert args[2].get('thread_id') == thread.id

    def test_push_interno_android_sin_webpush(self, db):
        """Android no debe recibir WebpushConfig: verificamos que el platform se pasa."""
        from backend.api import messaging_api
        from backend.api.messaging_models import (
            MessagingAppDevice, MessagingStaff, MessagingStaffChannel,
            MessagingStaffThread,
        )

        suffix = uuid.uuid4().hex[:8]
        admin = MessagingStaff(
            external_id=f"admin-and-{suffix}", name="Admin",
            email=f"admin-and-{suffix}@gestinem.es", role="admin", active=True,
        )
        member = MessagingStaff(
            external_id=f"member-and-{suffix}", name="Bea",
            email=f"member-and-{suffix}@gestinem.es", role="empleado", active=True,
        )
        db.add_all([admin, member])
        db.flush()
        db.add(MessagingStaffChannel(
            staff_external_id=member.external_id, channel="fiscal",
        ))
        thread = MessagingStaffThread(
            key=f"group:fiscal:{suffix}", kind="group", channel="fiscal",
        )
        db.add(thread)
        db.flush()
        device = MessagingAppDevice(
            user_type="staff", user_id=member.external_id, platform="android",
            push_token=f"android-token-{suffix}-" + "z" * 20, active=True,
        )
        db.add(device)
        db.flush()

        background = MagicMock()
        with patch.object(messaging_api, "fcm_configured", return_value=True):
            messaging_api._queue_internal_pushes(db, background, thread, admin)

        args = background.add_task.call_args.args
        # platform debe ser 'android', no 'web'
        assert args[3] == 'android'

    def test_desactivacion_solo_en_error_permanente(self, db):
        from backend.api.messaging_models import MessagingAppDevice
        import backend.api.messaging_api as api_mod
        from backend.api.messaging_firebase import FcmResult

        suffix = uuid.uuid4().hex[:8]
        device = MessagingAppDevice(
            user_type="staff", user_id=f"usr-{suffix}", platform="web",
            push_token=f"bad-token-{suffix}", active=True,
        )
        db.add(device)
        db.commit()

        # Patch send_fcm en el modulo messaging_api (referencia local).
        # Patch SessionLocal para que devuelva la sesion de test.
        mock_sl = MagicMock()
        mock_sl.return_value.__enter__ = MagicMock(return_value=db)
        mock_sl.return_value.__exit__ = MagicMock(return_value=False)

        with patch.object(api_mod, 'send_fcm', return_value=FcmResult(success=False, permanent_failure=True)):
            with patch.object(api_mod, 'SessionLocal', mock_sl):
                api_mod._send_push_and_handle(
                    device.push_token, {}, 'web', device.id,
                )

        db.refresh(device)
        assert device.active is False

    def test_error_transitorio_no_desactiva(self, db):
        from backend.api.messaging_models import MessagingAppDevice
        import backend.api.messaging_api as api_mod
        from backend.api.messaging_firebase import FcmResult

        suffix = uuid.uuid4().hex[:8]
        device = MessagingAppDevice(
            user_type="staff", user_id=f"usr2-{suffix}", platform="android",
            push_token=f"trans-token-{suffix}", active=True,
        )
        db.add(device)
        db.commit()

        with patch.object(api_mod, 'send_fcm', return_value=FcmResult(success=False, permanent_failure=False)):
            api_mod._send_push_and_handle(
                device.push_token, {}, 'android', device.id,
            )

        db.refresh(device)
        assert device.active is True
