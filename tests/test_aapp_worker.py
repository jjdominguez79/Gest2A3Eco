from __future__ import annotations

import base64
from pathlib import Path

import pytest

from aapp_worker.config import AappWorkerConfig
from aapp_worker.worker import AappWorker, _espera_reintento_segundos
from services.aapp.base import NotificacionDTO, ResultadoSync
from services.aapp.certificados import ResultadoCertificado
from aapp_worker.backend_client import AappBackendClient, CertificateMaterialError


class _Backend:
    def __init__(self, item):
        self.item = item
        self.completed = None
        self.failed = None
        self.dehu_notifications = None
        self.dev_notifications = None
        self.dev_registration_status = None

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
        return {"count": len(notifications), "created_count": len(notifications)}

    def upsert_dev_notifications(
        self, _item, notifications, *, registration_status, registration_message="",
    ):
        self.dev_notifications = notifications
        self.dev_registration_status = registration_status
        return {"count": len(notifications), "created_count": len(notifications)}

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
        role="certificates",
        interval_seconds=30,
        request_timeout_seconds=60,
        headless=True,
        diagnostic_dir=tmp_path / "diagnostico",
    )


def test_configuracion_exige_un_rol_valido(monkeypatch, tmp_path):
    secret = tmp_path / "worker-key.txt"
    secret.write_text("worker-secret", encoding="utf-8")
    monkeypatch.setenv("AAPP_BACKEND_URL", "https://api.example.test")
    monkeypatch.setenv("AAPP_WORKER_API_KEY_FILE", str(secret))
    monkeypatch.delenv("AAPP_WORKER_ROLE", raising=False)

    with pytest.raises(ValueError, match="AAPP_WORKER_ROLE"):
        AappWorkerConfig.from_environment()

    monkeypatch.setenv("AAPP_WORKER_ROLE", "notifications")
    assert AappWorkerConfig.from_environment().role == "notifications"


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


def test_worker_sigue_vivo_si_el_backend_falla_temporalmente(monkeypatch, tmp_path):
    worker = AappWorker(_config(tmp_path), backend=_Backend(None))
    calls = 0

    def run_once():
        nonlocal calls
        calls += 1
        if calls == 1:
            raise RuntimeError("500 Server Error")
        worker.stop()
        return False

    waits = []
    monkeypatch.setattr(worker, "run_once", run_once)
    monkeypatch.setattr(worker.stop_event, "wait", lambda seconds: waits.append(seconds))

    worker.run_forever()

    assert calls == 2
    assert waits == [30, 30]


def test_worker_no_reintenta_un_certificado_que_requiere_intervencion(tmp_path):
    item = {
        "id": "request-dehu-certificado-caducado",
        "organization_id": "org-1",
        "certificate_type": "DEHU_SYNC",
        "claim_token": "claim-token-valido",
        "attempt_count": 1,
        "parameters": {},
    }
    backend = _Backend(item)

    def material_no_disponible(_item):
        raise CertificateMaterialError(
            "El certificado digital del cliente caduco el 21/10/2026. "
            "Cargue el certificado renovado y vuelva a ejecutar la consulta.",
            needs_action=True,
        )

    backend.certificate_material = material_no_disponible

    assert AappWorker(_config(tmp_path), backend=backend).run_once() is True
    assert backend.completed is None
    assert backend.failed[2] == {
        "code": "certificate_material_unavailable",
        "needs_action": True,
        "retry_after_seconds": None,
    }
    assert "caduco el 21/10/2026" in backend.failed[1]


@pytest.mark.parametrize(
    ("intento", "espera"),
    [
        (1, 5 * 60),
        (2, 15 * 60),
        (3, 30 * 60),
        (4, 60 * 60),
        (5, 120 * 60),
        (6, None),
    ],
)
def test_dehu_reintenta_los_buzones_con_espera_escalonada(intento, espera):
    assert _espera_reintento_segundos({
        "certificate_type": "DEHU_SYNC",
        "attempt_count": intento,
    }) == espera


def test_otros_tramites_conservan_tres_intentos():
    assert _espera_reintento_segundos({
        "certificate_type": "TGSS_CORRIENTE",
        "attempt_count": 2,
    }) == 300
    assert _espera_reintento_segundos({
        "certificate_type": "TGSS_CORRIENTE",
        "attempt_count": 3,
    }) is None


def test_cliente_worker_envia_protocolo_vigente(tmp_path):
    class Response:
        def raise_for_status(self):
            return None

        def json(self):
            return {"item": None}

    class Session:
        def __init__(self):
            self.headers = None

        def post(self, _url, **kwargs):
            self.headers = kwargs["headers"]
            return Response()

    session = Session()
    backend = AappBackendClient(_config(tmp_path), session=session)

    assert backend.claim() is None
    assert session.headers["X-AAPP-Worker-Protocol"] == "4"
    assert session.headers["X-AAPP-Worker-Role"] == "certificates"


def test_cliente_worker_conserva_el_detalle_del_error_de_certificado(tmp_path):
    class Response:
        status_code = 409

        def raise_for_status(self):
            import requests
            raise requests.HTTPError("Conflict", response=self)

        def json(self):
            return {
                "detail": (
                    "El buzon esta activo, pero el cliente no tiene un "
                    "certificado digital configurado."
                ),
            }

    class Session:
        def post(self, _url, **_kwargs):
            return Response()

    backend = AappBackendClient(_config(tmp_path), session=Session())

    with pytest.raises(CertificateMaterialError) as raised:
        backend.certificate_material({
            "id": "request-1", "claim_token": "claim-token-valido",
        })

    assert raised.value.needs_action is True
    assert "no tiene un certificado digital configurado" in str(raised.value)


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


def test_publicacion_describe_vida_laboral_como_informe(tmp_path):
    class Response:
        def raise_for_status(self):
            return None

        def json(self):
            return {"id": "doc-vida-laboral"}

    class Session:
        def __init__(self):
            self.payload = None

        def post(self, _url, **kwargs):
            self.payload = kwargs["data"]
            return Response()

    pdf = Path(tmp_path) / "vida_laboral.pdf"
    pdf.write_bytes(b"%PDF-1.7\ninforme")
    session = Session()

    AappBackendClient(_config(tmp_path), session=session).publish_pdf({
        "id": "request-vida-laboral",
        "organization_id": "org-1",
        "certificate_type": "TGSS_VIDA_LABORAL",
        "certificate_name": "Informe de vida laboral",
        "requester_type": "client",
    }, pdf)

    assert session.payload["display_name"] == "Informe de vida laboral"
    assert session.payload["description"] == "Informe obtenido de TGSS"


def test_worker_dehu_solo_consulta_metadatos_y_elimina_pfx_temporal(monkeypatch, tmp_path):
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
            assert options.descargar_pdf is False
            assert options.nif_filtro is None
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
        None,
        "1 elemento(s) detectado(s); 1 asignado(s); 1 nuevo(s); "
        "0 descartada(s) sin buzon DEHu activo.",
    )
    assert backend.failed is None
    assert backend.dehu_notifications[0]["reference"] == "DEHU-1"
    assert backend.dehu_notifications[0]["document_id"] is None
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
        "1 elemento(s) detectado(s); 1 asignado(s); 1 nuevo(s); "
        "0 descartada(s) sin buzon DEHu activo.",
    )
    assert backend.dehu_notifications[0]["reference"] == "DEHU-2"
    assert backend.dehu_notifications[0]["document_id"] is None


def test_worker_dev_guarda_metadatos_y_estado_de_alta(monkeypatch, tmp_path):
    item = {
        "id": "request-dev-1",
        "organization_id": "org-1",
        "certificate_type": "DEV_SYNC",
        "claim_token": "claim-token-valido",
        "attempt_count": 1,
        "parameters": {
            "company_code": "E00999", "tax_id": "B12345678",
            "mailbox_id": "dev-1", "mailbox_name": "DGT / DEV",
        },
    }
    backend = _Backend(item)

    class Connector:
        def sincronizar(self, _mailbox, _material, options):
            assert options.descargar_pdf is False
            return ResultadoSync(
                ok=True, organismo_codigo="DEV", mensaje="ACTIVO: 1 elemento.",
                notificaciones=[NotificacionDTO(
                    referencia="DEV-1", asunto="Aviso DGT", estado="LEIDA",
                    nif_interesado="B12345678",
                    metadatos={"endpoint": "/WEB_NTRA_CONSULTA/listadoNotificaciones.faces"},
                )],
            )

    monkeypatch.setattr("aapp_worker.worker.obtener_conector", lambda _code: Connector())
    assert AappWorker(_config(tmp_path), backend=backend).run_once() is True
    assert backend.dev_registration_status == "ACTIVO"
    assert backend.dev_notifications[0]["reference"] == "DEV-1"
    assert "1 nueva(s)" in backend.completed[2]


def test_worker_dev_completa_con_aviso_explicito_si_no_esta_de_alta(monkeypatch, tmp_path):
    item = {
        "id": "request-dev-2", "organization_id": "org-1",
        "certificate_type": "DEV_SYNC", "claim_token": "claim-token-valido",
        "attempt_count": 1, "parameters": {},
    }
    backend = _Backend(item)

    class Connector:
        def sincronizar(self, *_args):
            return ResultadoSync(
                ok=True, organismo_codigo="DEV",
                mensaje="NO_ALTA: El titular no esta dado de alta en DEV.",
            )

    monkeypatch.setattr("aapp_worker.worker.obtener_conector", lambda _code: Connector())
    assert AappWorker(_config(tmp_path), backend=backend).run_once() is True
    assert backend.dev_registration_status == "NO_ALTA"
    assert backend.completed[2].startswith("DEV_NO_ALTA:")
