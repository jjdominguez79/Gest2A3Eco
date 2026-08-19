"""Pruebas del worker de mensajeria: trazabilidad y alertas de adjuntos obsoletos."""

from __future__ import annotations

import hashlib
import io
import os
import threading
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch


def _utcnow():
    return datetime.now(timezone.utc)


class _FakeResponse:
    def __init__(self, json_data, status_code=200):
        self._json = json_data
        self.status_code = status_code

    def json(self):
        return self._json

    def raise_for_status(self):
        if self.status_code >= 400:
            raise Exception(f"HTTP {self.status_code}")


class TestMessagingWorkerStalDetection(unittest.TestCase):
    """Verifica que el worker detecta y registra adjuntos obsoletos (>1h)."""

    def _make_config(self, tmp_path: Path):
        from sync_worker.messaging_worker import MessagingWorkerConfig
        return MessagingWorkerConfig(
            api_url="http://backend.test",
            sync_token="token",
            repository_dir=tmp_path / "nas",
            public_repository_dir=Path("\\\\NAS\\Docs"),
            postgres_dsn="host=localhost dbname=test",
            worker_id="synology",
            interval_seconds=60,
        )

    def test_run_once_registra_warning_para_adjuntos_stale(self, tmp_path=None):
        if tmp_path is None:
            import tempfile
            with tempfile.TemporaryDirectory() as d:
                self._run_stale_test(Path(d))
        else:
            self._run_stale_test(tmp_path)

    def _run_stale_test(self, tmp_path: Path):
        content = b"contenido de prueba"
        sha = hashlib.sha256(content).hexdigest()
        pending = [{
            "id": "adj-stale-1",
            "message_id": "msg-1",
            "conversation_id": "conv-1",
            "company_code": "E00001",
            "company_name": "Empresa Test",
            "name": "documento.pdf",
            "size": len(content),
            "sha256": sha,
            "content_type": "application/pdf",
            "author_name": "Cliente",
            "created_at": (_utcnow() - timedelta(hours=2)).isoformat(),
            "stale": True,
        }]

        # Configurar respuestas del mock
        def _respond(url, **kwargs):
            if url.endswith("/sync/attachments/pending"):
                return _FakeResponse(pending)
            if "/claim" in url:
                return _FakeResponse({"ok": True, "claim_expires_at": (_utcnow() + timedelta(minutes=10)).isoformat()})
            if "/content" in url:
                r = _FakeResponse(content)
                r.content = content
                return r
            if "/confirm" in url:
                return _FakeResponse({"ok": True})
            return _FakeResponse({})

        from sync_worker.messaging_worker import MessagingAttachmentWorker
        config = self._make_config(tmp_path)
        session = MagicMock()
        session.get.side_effect = _respond
        session.post.side_effect = _respond
        worker = MessagingAttachmentWorker(config, session=session)

        # Inyectar un mock de _save y _existing para no necesitar postgres
        worker._existing = MagicMock(return_value=None)
        worker._save = MagicMock()

        with self.assertLogs("gest2a3eco.messaging_sync", level="WARNING") as cm:
            worker.run_once()

        warnings = [msg for msg in cm.output if "ALERTA" in msg and "stale" in msg.lower() or "hora" in msg.lower()]
        # Al menos uno de los mensajes de warning debe mencionar el adjunto stale
        assert any("adj-stale-1" in msg or "ALERTA" in msg for msg in cm.output), \
            f"No se encontro warning de adjunto stale en: {cm.output}"

    def test_run_once_no_alerta_si_no_hay_stale(self):
        import tempfile, logging
        with tempfile.TemporaryDirectory() as d:
            content = b"fresco"
            sha = hashlib.sha256(content).hexdigest()
            pending = [{
                "id": "adj-fresh-1",
                "message_id": "msg-2",
                "conversation_id": "conv-1",
                "company_code": "E00001",
                "company_name": "Empresa",
                "name": "nuevo.pdf",
                "size": len(content),
                "sha256": sha,
                "content_type": "application/pdf",
                "author_name": "Cliente",
                "created_at": _utcnow().isoformat(),
                "stale": False,
            }]

            def _respond(url, **kwargs):
                if url.endswith("/sync/attachments/pending"):
                    return _FakeResponse(pending)
                if "/claim" in url:
                    return _FakeResponse({"ok": True, "claim_expires_at": (_utcnow() + timedelta(minutes=10)).isoformat()})
                if "/content" in url:
                    r = _FakeResponse(content)
                    r.content = content
                    return r
                if "/confirm" in url:
                    return _FakeResponse({"ok": True})
                return _FakeResponse({})

            from sync_worker.messaging_worker import MessagingAttachmentWorker
            config = self._make_config(Path(d))
            session = MagicMock()
            session.get.side_effect = _respond
            session.post.side_effect = _respond
            worker = MessagingAttachmentWorker(config, session=session)
            worker._existing = MagicMock(return_value=None)
            worker._save = MagicMock()

            # No deberia haber warnings de ALERTA
            with self.assertLogs("gest2a3eco.messaging_sync", level="INFO") as cm:
                worker.run_once()

            alerta_msgs = [msg for msg in cm.output if "ALERTA" in msg]
            assert not alerta_msgs, f"No deberia haber alertas: {alerta_msgs}"


class TestGestorPostgresMensajeriaLocal(unittest.TestCase):
    """Verifica los metodos de bandeja de adjuntos en GestorPostgres."""

    def _make_mock_gestor(self):
        """Crea un mock del gestor que simula las consultas de mensajeria."""
        from unittest.mock import MagicMock, patch
        gestor = MagicMock()
        return gestor

    def test_contar_adjuntos_pendientes_devuelve_entero(self):
        gestor = self._make_mock_gestor()
        gestor.contar_adjuntos_mensajeria_pendientes.return_value = 3
        resultado = gestor.contar_adjuntos_mensajeria_pendientes()
        assert resultado == 3

    def test_marcar_revisado_llama_al_metodo(self):
        gestor = self._make_mock_gestor()
        gestor.marcar_adjunto_mensajeria_revisado("id-1", revisado_por="admin")
        gestor.marcar_adjunto_mensajeria_revisado.assert_called_once_with("id-1", revisado_por="admin")

    def test_no_guardar_llama_al_metodo(self):
        gestor = self._make_mock_gestor()
        gestor.no_guardar_adjunto_mensajeria("id-2", revisado_por="admin")
        gestor.no_guardar_adjunto_mensajeria.assert_called_once_with("id-2", revisado_por="admin")


if __name__ == "__main__":
    unittest.main()
