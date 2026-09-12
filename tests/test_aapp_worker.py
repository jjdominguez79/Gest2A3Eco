from __future__ import annotations

import base64
from pathlib import Path

from aapp_worker.config import AappWorkerConfig
from aapp_worker.worker import AappWorker
from services.aapp.base import NotificacionDTO, ResultadoSync
from services.aapp.certificados import ResultadoCertificado
from aapp_worker.backend_client import AappBackendClient


class _Backend:
    def __init__(self, item):
        self.item = item
        self.completed = None
        self.failed = None
        self.dehu_notifications = None

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

    def publish_notification_pdf(self, _item, _notification, _path):
        return {"id": "notification-doc-1"}

    def upsert_dehu_notifications(self, _item, notifications):
        self.dehu_notifications = notifications
        return {"count": len(notifications)}

    def complete(self, item, document_id, summary=""):
        self.completed = (item["id"], document_id, summary)

    def fail(self, item, message, **kwargs):
        self.failed = (item["id"], message, kwargs)


class _Provider:
    def __init__(self):
        self.pfx_path = None
        self.parameters = None

    def obtener(self, material, _type, options):
        self.pfx_path = material.ruta_archivo
        self.parameters = options.parametros
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
        "parameters": {"contracting_party_tax_id": "B12345678"},
    }
    backend = _Backend(item)
    provider = _Provider()
    monkeypatch.setattr("aapp_worker.worker.obtener_proveedor", lambda _type: provider)

    assert AappWorker(_config(tmp_path), backend=backend).run_once() is True

    assert backend.completed == ("request-1", "doc-1", "POSITIVO")
    assert backend.failed is None
    assert provider.pfx_path is not None
    assert provider.parameters == {"contracting_party_tax_id": "B12345678"}
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


def test_publicacion_automatica_solo_para_solicitudes_flutter(tmp_path):
    class Response:
        def raise_for_status(self):
            return None

        def json(self):
            return {"id": "doc-1"}

    class Session:
        def __init__(self):
            self.payloads = []

        def post(self, _url, **kwargs):
            self.payloads.append(kwargs["data"])
            return Response()

    pdf = Path(tmp_path) / "certificado.pdf"
    pdf.write_bytes(b"%PDF-1.7\ncertificado")
    session = Session()
    backend = AappBackendClient(_config(tmp_path), session=session)
    base_item = {
        "id": "request-1",
        "organization_id": "org-1",
        "certificate_type": "AEAT_CORRIENTE",
    }

    backend.publish_pdf({**base_item, "requester_type": "desktop"}, pdf)
    backend.publish_pdf({**base_item, "requester_type": "client"}, pdf)

    assert session.payloads[0]["publish_to_client"] == "false"
    assert session.payloads[1]["publish_to_client"] == "true"
    assert int(session.payloads[0]["fiscal_year"]) >= 2026
    assert session.payloads[0]["document_date"].startswith("2026-")


def test_worker_dehu_publica_documento_y_elimina_pfx_temporal(monkeypatch, tmp_path):
    item = {
        "id": "request-dehu-1",
        "organization_id": "org-1",
        "certificate_type": "DEHU_SYNC",
        "claim_token": "claim-token-valido",
        "attempt_count": 1,
        "parameters": {
            "company_code": "E00001",
            "tax_id": "B12345678",
            "mailbox_id": "mailbox-1",
            "mailbox_name": "DEHu Cliente Uno",
        },
    }
    backend = _Backend(item)

    class Connector:
        certificate_path = None

        def sincronizar(self, _mailbox, material, options):
            self.certificate_path = material.ruta_archivo
            assert material.password == "clave"
            assert options.headless is True
            pdf = __import__("pathlib").Path(options.carpeta_descargas) / "notificacion.pdf"
            pdf.write_bytes(b"%PDF-1.7\nnotificacion")
            return ResultadoSync(
                ok=True,
                organismo_codigo="DEHU",
                notificaciones=[NotificacionDTO(
                    referencia="DEHU-1",
                    asunto="Notificacion de prueba",
                    pdf_path=str(pdf),
                )],
            )

    connector = Connector()
    monkeypatch.setattr("aapp_worker.worker.obtener_conector", lambda _code: connector)

    assert AappWorker(_config(tmp_path), backend=backend).run_once() is True

    assert backend.completed == (
        "request-dehu-1",
        "notification-doc-1",
        "1 notificacion(es) detectada(s); 1 documento(s) publicado(s).",
    )
    assert backend.failed is None
    assert backend.dehu_notifications[0]["reference"] == "DEHU-1"
    assert backend.dehu_notifications[0]["document_id"] == "notification-doc-1"
    assert connector.certificate_path is not None
    assert not __import__("pathlib").Path(connector.certificate_path).exists()


def test_worker_dehu_completa_aunque_no_haya_pdf(monkeypatch, tmp_path):
    item = {
        "id": "request-dehu-2",
        "organization_id": "org-1",
        "certificate_type": "DEHU_SYNC",
        "claim_token": "claim-token-valido",
        "attempt_count": 1,
        "parameters": {},
    }
    backend = _Backend(item)

    class Connector:
        def sincronizar(self, *_args):
            return ResultadoSync(
                ok=True,
                organismo_codigo="DEHU",
                notificaciones=[NotificacionDTO(referencia="DEHU-2")],
            )

    monkeypatch.setattr("aapp_worker.worker.obtener_conector", lambda _code: Connector())

    assert AappWorker(_config(tmp_path), backend=backend).run_once() is True
    assert backend.completed == (
        "request-dehu-2",
        None,
        "1 notificacion(es) detectada(s); 0 documento(s) publicado(s).",
    )
    assert backend.dehu_notifications[0]["reference"] == "DEHU-2"
    assert backend.dehu_notifications[0]["document_id"] is None
