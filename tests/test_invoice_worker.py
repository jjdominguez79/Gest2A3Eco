"""Tests del invoice worker con adaptadores simulados.

Verifica el flujo completo: claim → import → PDF → upload → publish → email → FCM.
Cada paso es idempotente; las caidas no duplican datos.
"""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import responses

os.environ.setdefault("INVOICE_WORKER_API_TOKEN", "test-token")
os.environ.setdefault("INVOICE_WORKER_DESKTOP_DSN", "")

from invoice_worker.config import WorkerConfig
from invoice_worker.worker import InvoiceWorker, RealEmailSender


# ---------------------------------------------------------------------------
# Mock adapters
# ---------------------------------------------------------------------------

class MockGestor:
    """Simula el gestor del escritorio en memoria."""

    def __init__(self):
        self.terceros: dict[str, dict] = {}
        self.terceros_empresa: list[dict] = []
        self.subcuentas: list[dict] = []
        self.facturas: dict[str, dict] = {}
        self.empresas: dict[str, dict] = {
            "TEST01": {
                "codigo": "TEST01",
                "digitos_plan": 8,
                "nombre": "Empresa Test",
            }
        }
        self._next_id = 1

    def get_empresa(self, codigo: str) -> dict | None:
        return self.empresas.get(codigo)

    def get_tercero_by_nif_normalizado(self, nif: str) -> dict | None:
        for t in self.terceros.values():
            if t.get("nif_normalizado") == nif:
                return t
        return None

    def upsert_tercero(self, tercero: dict) -> str:
        tid = f"t{self._next_id}"
        self._next_id += 1
        tercero["id"] = tid
        self.terceros[tid] = tercero
        return tid

    def upsert_tercero_empresa(self, rel: dict) -> None:
        self.terceros_empresa.append(rel)

    def upsert_maestro_subcuenta(self, datos: dict) -> int:
        self.subcuentas.append(datos)
        return len(self.subcuentas)

    def get_maestro_subcuenta_por_subcuenta(self, codigo: str, sub: str) -> dict | None:
        for s in self.subcuentas:
            if s.get("codigo_empresa") == codigo and s.get("subcuenta") == sub:
                return s
        return None

    def listar_maestro_subcuentas_empresa(self, codigo: str, tipo=None, activo=True) -> list:
        return [
            s for s in self.subcuentas
            if s.get("codigo_empresa") == codigo
            and (tipo is None or s.get("tipo_subcuenta") == tipo)
        ]

    def upsert_factura_emitida(self, factura: dict) -> str:
        fid = factura.get("id", f"f{self._next_id}")
        self._next_id += 1
        self.facturas[fid] = factura
        return fid


class MockRenderer:
    """Simula generacion de PDF escribiendo un archivo dummy."""

    def __init__(self):
        self.calls: list[dict] = []

    def render(self, empresa_conf, fac, cliente, totales, template_path, pdf_path):
        self.calls.append({
            "empresa": empresa_conf,
            "fac": fac,
            "cliente": cliente,
            "totales": totales,
        })
        Path(pdf_path).write_bytes(b"%PDF-1.4 " + b"X" * 200)
        return pdf_path


class MockEmailSender:
    """Simula envio de email."""

    def __init__(self):
        self.sent: list[dict] = []

    def send(self, *, sender, to, subject, body, attachments=None):
        self.sent.append({
            "sender": sender,
            "to": to,
            "subject": subject,
            "body": body,
            "attachments_count": len(attachments or []),
        })
        return {"message_id": f"mock-msg-{len(self.sent)}"}


class MockFcmSender:
    """Simula envio FCM."""

    def __init__(self):
        self.sent: list[dict] = []

    def send(self, push_token, payload, *, platform="android"):
        self.sent.append({
            "token": push_token,
            "payload": payload,
            "platform": platform,
        })
        return True


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

SAMPLE_PAYLOAD = {
    "organization": {
        "company_code": "TEST01",
        "name": "Empresa Test SL",
        "tax_id": "B99999999",
        "address": "Calle Test 1",
        "postal_code": "28001",
        "city": "Madrid",
        "province": "Madrid",
        "country": "ES",
        "phone": "911234567",
        "email": "info@test.es",
    },
    "customer": {
        "tax_id": "B-12.345.678",
        "legal_name": "Cliente Test SL",
        "address": "Av. Prueba 5",
        "postal_code": "08001",
        "city": "Barcelona",
        "province": "Barcelona",
        "country": "ES",
        "email": "cliente@test.com",
        "phone": "931234567",
    },
    "invoice": {
        "series_code": "WEB",
        "invoice_number": 1,
        "invoice_date": "2026-06-15",
        "fiscal_year": 2026,
        "subtotal": "500.00",
        "total_vat": "105.00",
        "withholding_rate": "0",
        "withholding_amount": "0",
        "total": "605.00",
        "currency": "EUR",
        "payment_method": "Transferencia",
        "notes": "Factura de prueba",
        "recipient_email": "cliente@test.com",
    },
    "lines": [
        {
            "description": "Servicio de consultoria",
            "quantity": "10",
            "unit_price": "50.00",
            "discount_percent": "0",
            "vat_rate": "21.00",
            "vat_amount": "105.00",
            "line_total": "500.00",
        },
    ],
    "push_tokens": [
        {"token": "fcm-token-1", "platform": "android"},
        {"token": "fcm-token-2", "platform": "web"},
    ],
}


def _make_config(tmp_path: Path) -> WorkerConfig:
    template_dir = tmp_path / "templates"
    template_dir.mkdir()
    (template_dir / "factura_emitida.docx").write_bytes(b"PK fake docx")

    pdf_dir = tmp_path / "pdfs"
    pdf_dir.mkdir()

    return WorkerConfig(
        api_base_url="http://test-api/api/v1/messaging/client/invoicing",
        worker_id="test-worker-1",
        lease_minutes=10,
        poll_interval_seconds=5,
        word_template_dir=str(template_dir),
        pdf_output_dir=str(pdf_dir),
        api_token="test-token",
        desktop_dsn="",
        graph_sender_mailbox="test@gestinem.es",
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestImportToDesktop:
    """Importacion de tercero y factura al escritorio."""

    def test_creates_tercero_and_factura(self, tmp_path):
        config = _make_config(tmp_path)
        gestor = MockGestor()
        worker = InvoiceWorker(config, gestor=gestor)

        worker._import_to_desktop("inv-001", SAMPLE_PAYLOAD)

        # Tercero creado
        assert len(gestor.terceros) == 1
        tercero = list(gestor.terceros.values())[0]
        assert tercero["nif_normalizado"] == "B12345678"
        assert tercero["nombre"] == "Cliente Test SL"

        # Subcuenta 430 asignada
        assert len(gestor.subcuentas) == 1
        sub = gestor.subcuentas[0]
        assert sub["subcuenta"].startswith("430")
        assert len(sub["subcuenta"]) == 8  # digitos_plan=8

        # Relacion tercero-empresa
        assert len(gestor.terceros_empresa) == 1

        # Factura importada
        assert len(gestor.facturas) == 1
        fac = list(gestor.facturas.values())[0]
        assert fac["serie"] == "WEB"
        assert fac["numero"] == 1
        assert fac["codigo_empresa"] == "TEST01"

    def test_idempotent_import(self, tmp_path):
        """Segunda importacion no duplica tercero ni subcuenta."""
        config = _make_config(tmp_path)
        gestor = MockGestor()
        worker = InvoiceWorker(config, gestor=gestor)

        worker._import_to_desktop("inv-001", SAMPLE_PAYLOAD)
        worker._import_to_desktop("inv-001", SAMPLE_PAYLOAD)

        # Solo 1 tercero (segunda vez lo encuentra por NIF)
        assert len(gestor.terceros) == 1
        # Solo 1 subcuenta (segunda vez la encuentra existente)
        assert len(gestor.subcuentas) == 1

    def test_missing_company_raises(self, tmp_path):
        config = _make_config(tmp_path)
        gestor = MockGestor()
        worker = InvoiceWorker(config, gestor=gestor)

        payload = {**SAMPLE_PAYLOAD, "organization": {"company_code": "NOEXISTE"}}
        with pytest.raises(ValueError, match="no existe en escritorio"):
            worker._import_to_desktop("inv-002", payload)

    def test_empty_nif_raises(self, tmp_path):
        config = _make_config(tmp_path)
        gestor = MockGestor()
        worker = InvoiceWorker(config, gestor=gestor)

        payload = {
            **SAMPLE_PAYLOAD,
            "customer": {**SAMPLE_PAYLOAD["customer"], "tax_id": ""},
        }
        with pytest.raises(ValueError, match="NIF del cliente vacio"):
            worker._import_to_desktop("inv-003", payload)

    def test_withholding_applied(self, tmp_path):
        config = _make_config(tmp_path)
        gestor = MockGestor()
        worker = InvoiceWorker(config, gestor=gestor)

        payload_wh = {
            **SAMPLE_PAYLOAD,
            "invoice": {
                **SAMPLE_PAYLOAD["invoice"],
                "withholding_rate": "15",
                "withholding_amount": "75.00",
            },
        }
        worker._import_to_desktop("inv-wh", payload_wh)

        fac = list(gestor.facturas.values())[0]
        assert fac["retencion_aplica"] is True
        assert fac["retencion_pct"] == 15.0
        assert fac["retencion_importe"] == -75.0


class TestResolveSubcuenta430:
    def test_assigns_first_subcuenta(self, tmp_path):
        config = _make_config(tmp_path)
        gestor = MockGestor()
        worker = InvoiceWorker(config, gestor=gestor)

        sub = worker._resolve_subcuenta_430(gestor, "TEST01", "B12345678", 8)
        assert sub == "43000001"

    def test_assigns_next_sequential(self, tmp_path):
        config = _make_config(tmp_path)
        gestor = MockGestor()
        # Preexisting subcuenta
        gestor.subcuentas.append({
            "codigo_empresa": "TEST01",
            "subcuenta": "43000005",
            "tipo_subcuenta": "cliente",
            "nif_snapshot": "A11111111",
        })
        worker = InvoiceWorker(config, gestor=gestor)

        sub = worker._resolve_subcuenta_430(gestor, "TEST01", "B12345678", 8)
        assert sub == "43000006"

    def test_finds_existing_by_nif(self, tmp_path):
        config = _make_config(tmp_path)
        gestor = MockGestor()
        gestor.subcuentas.append({
            "codigo_empresa": "TEST01",
            "subcuenta": "43000003",
            "tipo_subcuenta": "cliente",
            "nif_snapshot": "B12345678",
        })
        worker = InvoiceWorker(config, gestor=gestor)

        sub = worker._resolve_subcuenta_430(gestor, "TEST01", "B12345678", 8)
        assert sub == "43000003"  # reutiliza la existente


class TestRenderPdf:
    def test_calls_renderer_and_creates_file(self, tmp_path):
        config = _make_config(tmp_path)
        renderer = MockRenderer()
        worker = InvoiceWorker(config, renderer=renderer)

        pdf_path = worker._render_pdf("inv-001", SAMPLE_PAYLOAD)

        assert pdf_path.exists()
        assert pdf_path.stat().st_size > 0
        assert len(renderer.calls) == 1
        assert renderer.calls[0]["empresa"]["nombre"] == "Empresa Test SL"

    def test_idempotent_skips_existing_pdf(self, tmp_path):
        config = _make_config(tmp_path)
        renderer = MockRenderer()
        worker = InvoiceWorker(config, renderer=renderer)

        pdf1 = worker._render_pdf("inv-001", SAMPLE_PAYLOAD)
        pdf2 = worker._render_pdf("inv-001", SAMPLE_PAYLOAD)

        assert pdf1 == pdf2
        assert len(renderer.calls) == 1  # solo renderizo una vez


class TestSendEmail:
    @responses.activate
    def test_sends_email_with_attachment(self, tmp_path):
        config = _make_config(tmp_path)
        email_sender = MockEmailSender()
        worker = InvoiceWorker(config, email_sender=email_sender)

        # Crear PDF dummy
        pdf_path = tmp_path / "pdfs" / "WEB-000001.pdf"
        pdf_path.parent.mkdir(parents=True, exist_ok=True)
        pdf_path.write_bytes(b"%PDF-1.4 test")

        # Mock del endpoint mark_emailed
        responses.add(
            responses.POST,
            f"{config.api_base_url}/worker/invoice/inv-001/emailed",
            json={"status": "ok"},
        )

        worker._send_email("inv-001", SAMPLE_PAYLOAD, pdf_path)

        assert len(email_sender.sent) == 1
        msg = email_sender.sent[0]
        assert msg["to"] == "cliente@test.com"
        assert "WEB-000001" in msg["subject"]
        assert msg["attachments_count"] == 1

    @responses.activate
    def test_no_recipient_still_marks_emailed(self, tmp_path):
        config = _make_config(tmp_path)
        email_sender = MockEmailSender()
        worker = InvoiceWorker(config, email_sender=email_sender)

        payload = {
            **SAMPLE_PAYLOAD,
            "invoice": {**SAMPLE_PAYLOAD["invoice"], "recipient_email": ""},
        }

        responses.add(
            responses.POST,
            f"{config.api_base_url}/worker/invoice/inv-002/emailed",
            json={"status": "ok"},
        )

        pdf_path = tmp_path / "dummy.pdf"
        pdf_path.write_bytes(b"%PDF")
        worker._send_email("inv-002", payload, pdf_path)

        # No se envio email pero si se marco
        assert len(email_sender.sent) == 0
        assert len(responses.calls) == 1  # mark_emailed llamado

    @responses.activate
    def test_send_failure_does_not_mark_emailed(self, tmp_path):
        config = _make_config(tmp_path)

        class FailingEmailSender:
            def send(self, **_kwargs):
                raise ConnectionError("Graph no disponible")

        worker = InvoiceWorker(config, email_sender=FailingEmailSender())
        pdf_path = tmp_path / "dummy.pdf"
        pdf_path.write_bytes(b"%PDF")

        with pytest.raises(ConnectionError, match="Graph no disponible"):
            worker._send_email("inv-fail", SAMPLE_PAYLOAD, pdf_path)

        assert not responses.calls

    def test_real_adapter_converts_graph_arguments(self, monkeypatch, tmp_path):
        pdf_path = tmp_path / "factura.pdf"
        pdf_path.write_bytes(b"%PDF")
        captured = {}

        class GraphStub:
            def send(self, **kwargs):
                captured.update(kwargs)
                return type("Result", (), {"internet_message_id": "msg-1"})()

        monkeypatch.setattr(
            "services.graph_mail_service.GraphMailService",
            lambda: GraphStub(),
        )
        sender = RealEmailSender()

        result = sender.send(
            sender="oficina@example.test",
            to="cliente@example.test",
            subject="Factura",
            body="Adjuntamos factura",
            attachments=[{"path": str(pdf_path), "content": b"ignored"}],
        )

        assert captured["to"] == ["cliente@example.test"]
        assert captured["attachments"] == [str(pdf_path)]
        assert result == {"message_id": "msg-1"}


class TestSendFcm:
    def test_sends_to_all_tokens(self, tmp_path):
        config = _make_config(tmp_path)
        fcm = MockFcmSender()
        worker = InvoiceWorker(config, fcm_sender=fcm)

        worker._send_fcm("inv-001", SAMPLE_PAYLOAD)

        assert len(fcm.sent) == 2
        assert fcm.sent[0]["token"] == "fcm-token-1"
        assert fcm.sent[0]["platform"] == "android"
        assert fcm.sent[1]["token"] == "fcm-token-2"
        assert fcm.sent[1]["platform"] == "web"
        assert fcm.sent[0]["payload"]["type"] == "invoice_processed"

    def test_no_tokens_no_error(self, tmp_path):
        config = _make_config(tmp_path)
        fcm = MockFcmSender()
        worker = InvoiceWorker(config, fcm_sender=fcm)

        payload = {**SAMPLE_PAYLOAD, "push_tokens": []}
        worker._send_fcm("inv-no-tokens", payload)

        assert len(fcm.sent) == 0

    def test_fcm_error_does_not_propagate(self, tmp_path):
        """FCM es best-effort; los errores no bloquean el flujo."""
        config = _make_config(tmp_path)

        class FailingFcm:
            def send(self, token, payload, *, platform="android"):
                raise ConnectionError("FCM down")

        worker = InvoiceWorker(config, fcm_sender=FailingFcm())
        # No debe lanzar excepcion
        worker._send_fcm("inv-fail", SAMPLE_PAYLOAD)


class TestFullProcess:
    """Test del flujo completo _process con todos los pasos mockeados."""

    @responses.activate
    def test_full_flow(self, tmp_path):
        config = _make_config(tmp_path)
        gestor = MockGestor()
        renderer = MockRenderer()
        email_sender = MockEmailSender()
        fcm_sender = MockFcmSender()

        worker = InvoiceWorker(
            config,
            gestor=gestor,
            renderer=renderer,
            email_sender=email_sender,
            fcm_sender=fcm_sender,
        )

        base = config.api_base_url

        # Mock all API calls
        responses.add(responses.GET, f"{base}/worker/invoice/inv-full/payload",
                      json=SAMPLE_PAYLOAD)
        responses.add(responses.POST, f"{base}/worker/invoice/inv-full/import-confirmed",
                      json={"status": "ok"})
        responses.add(responses.POST, f"{base}/worker/invoice/inv-full/pdf",
                      json={"status": "ok"})
        responses.add(responses.POST, f"{base}/worker/invoice/inv-full/publish-document",
                      json={"document_id": "doc-123"})
        responses.add(responses.POST, f"{base}/worker/invoice/inv-full/emailed",
                      json={"status": "ok"})

        worker._process({"invoice_id": "inv-full"})

        # Verify each step executed
        assert len(gestor.facturas) == 1  # import
        assert len(renderer.calls) == 1   # PDF
        assert len(email_sender.sent) == 1  # email
        assert len(fcm_sender.sent) == 2  # FCM (2 tokens)

        # Verify API calls made in correct order
        api_paths = [c.request.path_url for c in responses.calls]
        assert "/payload" in api_paths[0]
        assert "/import-confirmed" in api_paths[1]
        assert "/pdf" in api_paths[2]
        assert "/publish-document" in api_paths[3]
        assert "/emailed" in api_paths[4]

    @responses.activate
    def test_error_reported_on_failure(self, tmp_path):
        config = _make_config(tmp_path)
        gestor = MockGestor()
        worker = InvoiceWorker(config, gestor=gestor)

        base = config.api_base_url

        # Payload con empresa que no existe -> error en _import_to_desktop
        bad_payload = {
            **SAMPLE_PAYLOAD,
            "organization": {**SAMPLE_PAYLOAD["organization"], "company_code": "NOPE"},
        }
        responses.add(responses.GET, f"{base}/worker/invoice/inv-err/payload",
                      json=bad_payload)
        responses.add(responses.POST, f"{base}/worker/invoice/inv-err/error",
                      json={"status": "ok"})

        worker._process({"invoice_id": "inv-err"})

        # Error reported
        error_calls = [c for c in responses.calls if "/error" in c.request.path_url]
        assert len(error_calls) == 1
        body = json.loads(error_calls[0].request.body)
        assert "no existe en escritorio" in body["error"]


class TestClaim:
    @responses.activate
    def test_claim_returns_data(self, tmp_path):
        config = _make_config(tmp_path)
        worker = InvoiceWorker(config)

        responses.add(
            responses.POST, f"{config.api_base_url}/worker/claim",
            json={"claimed": True, "invoice_id": "inv-42"},
        )
        result = worker._claim()
        assert result == {"claimed": True, "invoice_id": "inv-42"}

    @responses.activate
    def test_claim_returns_none_when_empty(self, tmp_path):
        config = _make_config(tmp_path)
        worker = InvoiceWorker(config)

        responses.add(
            responses.POST, f"{config.api_base_url}/worker/claim",
            json={"claimed": False},
        )
        result = worker._claim()
        assert result is None
