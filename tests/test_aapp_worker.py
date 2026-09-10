from __future__ import annotations

import base64

from aapp_worker.config import AappWorkerConfig
from aapp_worker.worker import AappWorker
from services.aapp.certificados import ResultadoCertificado


class _Backend:
    def __init__(self, item):
        self.item = item
        self.completed = None
        self.failed = None

    def claim(self):
        return self.item

    def certificate_material(self, _item):
        return {
            "file_name": "piloto.pfx",
            "pfx_base64": base64.b64encode(b"pfx-secreto").decode(),
            "password": "clave",
            "valid_until": "2027-09-10T00:00:00+00:00",
        }

    def publish_pdf(self, _item, _path):
        return {"id": "doc-1"}

    def complete(self, item, document_id, summary=""):
        self.completed = (item["id"], document_id, summary)

    def fail(self, item, message, **kwargs):
        self.failed = (item["id"], message, kwargs)


class _Provider:
    def __init__(self):
        self.pfx_path = None

    def obtener(self, material, _type, options):
        self.pfx_path = material.ruta_archivo
        assert material.password == "clave"
        with open(options.ruta_pdf_destino, "wb") as stream:
            stream.write(b"%PDF-1.7\ncertificado")
        return ResultadoCertificado(
            ok=True,
            tipo="AEAT_CORRIENTE",
            estado="OBTENIDO",
            pdf_path=options.ruta_pdf_destino,
            resultado="POSITIVO",
        )


def _config(tmp_path):
    return AappWorkerConfig(
        backend_url="https://api.example.test",
        api_key="test",
        interval_seconds=30,
        request_timeout_seconds=60,
        headless=True,
        diagnostic_dir=tmp_path / "diagnostico",
    )


def test_worker_publica_y_elimina_material_temporal(monkeypatch, tmp_path):
    item = {
        "id": "request-1",
        "organization_id": "org-1",
        "certificate_type": "AEAT_CORRIENTE",
        "certificate_name": "Estar al corriente",
        "claim_token": "claim-token-valido",
        "attempt_count": 1,
    }
    backend = _Backend(item)
    provider = _Provider()
    monkeypatch.setattr("aapp_worker.worker.obtener_proveedor", lambda _type: provider)

    assert AappWorker(_config(tmp_path), backend=backend).run_once() is True

    assert backend.completed == ("request-1", "doc-1", "POSITIVO")
    assert backend.failed is None
    assert provider.pfx_path is not None
    assert not __import__("pathlib").Path(provider.pfx_path).exists()


def test_worker_deja_intervencion_sin_publicar(monkeypatch, tmp_path):
    item = {
        "id": "request-2",
        "organization_id": "org-1",
        "certificate_type": "TGSS_CORRIENTE",
        "claim_token": "claim-token-valido",
        "attempt_count": 1,
    }
    backend = _Backend(item)

    class PendingProvider:
        def obtener(self, *_args):
            return ResultadoCertificado(
                ok=False,
                tipo="TGSS_CORRIENTE",
                estado="PENDIENTE",
                mensaje="La sede requiere confirmacion",
            )

    monkeypatch.setattr(
        "aapp_worker.worker.obtener_proveedor", lambda _type: PendingProvider(),
    )

    AappWorker(_config(tmp_path), backend=backend).run_once()

    assert backend.completed is None
    assert backend.failed[2]["needs_action"] is True


def test_worker_sin_trabajo_no_hace_nada(tmp_path):
    backend = _Backend(None)

    assert AappWorker(_config(tmp_path), backend=backend).run_once() is False
    assert backend.completed is None
    assert backend.failed is None
