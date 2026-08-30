"""Tests del invoice worker con adaptadores simulados.

Verifica el flujo completo: claim -> import -> PDF -> upload -> publish -> email -> FCM.
Cada paso es idempotente; las caidas no duplican datos.
El worker delega el envio de email y FCM al backend.
"""

from __future__ import annotations

import json
import os
from copy import deepcopy
from pathlib import Path

import pytest
import responses

os.environ.setdefault("INVOICE_WORKER_API_TOKEN", "test-token")
os.environ.setdefault("INVOICE_WORKER_DESKTOP_DSN", "")
# Permitir secretos via entorno en tests (sin Credential Manager real)
os.environ.setdefault("INVOICE_WORKER_ALLOW_ENV_SECRETS", "true")

from invoice_worker.config import WorkerConfig
from invoice_worker.worker import InvoiceWorker


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

    def get_tercero_empresa(self, codigo_empresa, tercero_id, ejercicio):
        for relation in self.terceros_empresa:
            if (
                relation.get("codigo_empresa") == codigo_empresa
                and relation.get("tercero_id") == tercero_id
            ):
                return relation
        return None

    def upsert_tercero_empresa(self, rel: dict) -> None:
        for index, current in enumerate(self.terceros_empresa):
            if (
                current.get("codigo_empresa") == rel.get("codigo_empresa")
                and current.get("ejercicio") == rel.get("ejercicio")
                and current.get("tercero_id") == rel.get("tercero_id")
            ):
                self.terceros_empresa[index] = rel
                return
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

    def enviar_facturas_emitidas_a_contabilidad(self, codigo, ejercicio, ids):
        for factura_id in ids:
            if factura_id in self.facturas:
                self.facturas[factura_id]["estado_contable"] = "pendiente"


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

    log_dir = tmp_path / "logs"
    log_dir.mkdir()

    return WorkerConfig(
        api_base_url="http://test-api/api/v1/messaging/client/invoicing",
        worker_id="test-worker-1",
        lease_minutes=10,
        poll_interval_seconds=5,
        max_retries=5,
        word_template_dir=str(template_dir),
        pdf_output_dir=str(pdf_dir),
        log_dir=str(log_dir),
        api_token="test-token",
        desktop_dsn="",
        sender_mailbox="test@gestinem.es",
    )


def _payload_with_synced_customer(worker, gestor) -> dict:
    payload = deepcopy(SAMPLE_PAYLOAD)
    tercero_id, subcuenta = worker._import_customer_to_desktop(
        payload["organization"], payload["customer"],
    )
    payload["customer"]["desktop_tercero_id"] = tercero_id
    payload["customer"]["desktop_subcuenta"] = subcuenta
    return payload


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestImportToDesktop:
    """Importacion de tercero y factura al escritorio."""

    def test_alta_flutter_reutiliza_430_existente_del_tercero(self, tmp_path):
        config = _make_config(tmp_path)
        gestor = MockGestor()
        tercero_id = gestor.upsert_tercero({
            "nif": "B12345678",
            "nif_normalizado": "B12345678",
            "nombre": "Cliente existente",
        })
        gestor.upsert_tercero_empresa({
            "codigo_empresa": "TEST01",
            "ejercicio": 0,
            "tercero_id": tercero_id,
            "subcuenta_cliente": "43000009",
        })
        worker = InvoiceWorker(config, gestor=gestor)

        result = worker._import_customer_to_desktop(
            SAMPLE_PAYLOAD["organization"], SAMPLE_PAYLOAD["customer"],
        )

        assert result == (tercero_id, "43000009")
        assert gestor.subcuentas[0]["subcuenta"] == "43000009"

    def test_imports_factura_for_previously_synced_customer(self, tmp_path):
        config = _make_config(tmp_path)
        gestor = MockGestor()
        worker = InvoiceWorker(config, gestor=gestor)

        payload = _payload_with_synced_customer(worker, gestor)
        worker._import_to_desktop("inv-001", payload)

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
        assert fac["estado_contable"] == "pendiente"

    def test_idempotent_import(self, tmp_path):
        """Segunda importacion no duplica tercero ni subcuenta."""
        config = _make_config(tmp_path)
        gestor = MockGestor()
        worker = InvoiceWorker(config, gestor=gestor)

        payload = _payload_with_synced_customer(worker, gestor)
        worker._import_to_desktop("inv-001", payload)
        worker._import_to_desktop("inv-001", payload)

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
            **_payload_with_synced_customer(worker, gestor),
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
    def test_snapshot_de_emision_prevalece_y_conserva_enlace_desktop(self):
        payload = deepcopy(SAMPLE_PAYLOAD)
        payload["customer"]["desktop_tercero_id"] = "ter-1"
        payload["customer"]["desktop_subcuenta"] = "43000001"
        payload["issued_snapshot"] = json.dumps({
            "organization": {"company_code": "TEST01", "name": "EMISOR AL EMITIR"},
            "customer": {"tax_id": "B12345678", "legal_name": "CLIENTE AL EMITIR"},
            "invoice": {"series_code": "APP", "invoice_number": 7},
            "lines": [{"description": "LINEA AL EMITIR"}],
        })

        result = InvoiceWorker._apply_issued_snapshot(payload)

        assert result["customer"]["legal_name"] == "CLIENTE AL EMITIR"
        assert result["customer"]["desktop_subcuenta"] == "43000001"
        assert result["organization"]["name"] == "EMISOR AL EMITIR"
        assert result["invoice"]["series_code"] == "APP"
        assert result["lines"][0]["description"] == "LINEA AL EMITIR"

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


class TestRequestEmail:
    """El worker delega el envio de email al backend."""

    @responses.activate
    def test_requests_email_via_backend(self, tmp_path):
        config = _make_config(tmp_path)
        worker = InvoiceWorker(config)
        base = config.api_base_url

        responses.add(
            responses.POST,
            f"{base}/worker/invoice/inv-001/send-email",
            json={"status": "ok", "message_id": "msg-123"},
        )

        worker._request_email("inv-001", SAMPLE_PAYLOAD)

        assert len(responses.calls) == 1
        body = json.loads(responses.calls[0].request.body)
        assert body["recipient_email"] == "cliente@test.com"
        assert body["sender_mailbox"] == "test@gestinem.es"

    @responses.activate
    def test_already_sent_is_handled(self, tmp_path):
        config = _make_config(tmp_path)
        worker = InvoiceWorker(config)
        base = config.api_base_url

        responses.add(
            responses.POST,
            f"{base}/worker/invoice/inv-001/send-email",
            json={"status": "ok", "already_sent": True},
        )

        worker._request_email("inv-001", SAMPLE_PAYLOAD)
        assert len(responses.calls) == 1


class TestRequestFcm:
    """El worker delega FCM al backend (best-effort)."""

    @responses.activate
    def test_requests_fcm_via_backend(self, tmp_path):
        config = _make_config(tmp_path)
        worker = InvoiceWorker(config)
        base = config.api_base_url

        responses.add(
            responses.POST,
            f"{base}/worker/invoice/inv-001/send-fcm",
            json={"status": "ok", "sent": 2, "errors": 0},
        )

        worker._request_fcm("inv-001")
        assert len(responses.calls) == 1

    @responses.activate
    def test_fcm_error_does_not_propagate(self, tmp_path):
        """FCM es best-effort; los errores no bloquean el flujo."""
        config = _make_config(tmp_path)
        worker = InvoiceWorker(config)
        base = config.api_base_url

        responses.add(
            responses.POST,
            f"{base}/worker/invoice/inv-001/send-fcm",
            status=500,
        )

        # No debe lanzar excepcion
        worker._request_fcm("inv-001")


class TestFullProcess:
    """Test del flujo completo _process con todos los pasos mockeados."""

    @responses.activate
    def test_full_flow(self, tmp_path):
        config = _make_config(tmp_path)
        gestor = MockGestor()
        renderer = MockRenderer()

        worker = InvoiceWorker(
            config,
            gestor=gestor,
            renderer=renderer,
        )

        base = config.api_base_url
        payload = _payload_with_synced_customer(worker, gestor)

        # Mock all API calls
        responses.add(responses.GET, f"{base}/worker/invoice/inv-full/status",
                      json={"invoice_status": "claimed", "pdf_uploaded": False,
                            "document_published": False})
        responses.add(responses.GET, f"{base}/worker/invoice/inv-full/payload",
                      json=payload)
        responses.add(responses.POST, f"{base}/worker/invoice/inv-full/import-confirmed",
                      json={"status": "ok"})
        responses.add(responses.POST, f"{base}/worker/invoice/inv-full/pdf",
                      json={"status": "ok"})
        responses.add(responses.POST, f"{base}/worker/invoice/inv-full/publish-document",
                      json={"document_id": "doc-123"})
        responses.add(responses.POST, f"{base}/worker/invoice/inv-full/send-email",
                      json={"status": "ok", "message_id": "msg-1"})
        responses.add(responses.POST, f"{base}/worker/invoice/inv-full/send-fcm",
                      json={"status": "ok", "sent": 2, "errors": 0})

        worker._process({"invoice_id": "inv-full"})

        # Verify each step executed
        assert len(gestor.facturas) == 1  # import
        assert len(renderer.calls) == 1   # PDF

        # Verify API calls made
        api_paths = [c.request.path_url for c in responses.calls]
        assert any("/status" in p for p in api_paths)
        assert any("/payload" in p for p in api_paths)
        assert any("/import-confirmed" in p for p in api_paths)
        assert any("/pdf" in p for p in api_paths)
        assert any("/publish-document" in p for p in api_paths)
        assert any("/send-email" in p for p in api_paths)
        assert any("/send-fcm" in p for p in api_paths)

    @responses.activate
    def test_recovery_skips_completed_steps(self, tmp_path):
        """Si el worker se recupera, no repite pasos completados."""
        config = _make_config(tmp_path)
        gestor = MockGestor()
        renderer = MockRenderer()

        worker = InvoiceWorker(config, gestor=gestor, renderer=renderer)
        base = config.api_base_url

        # Status indica que PDF ya esta subido y documento publicado
        responses.add(responses.GET, f"{base}/worker/invoice/inv-rec/status",
                      json={"invoice_status": "rendered", "pdf_uploaded": True,
                            "document_published": True})
        responses.add(responses.GET, f"{base}/worker/invoice/inv-rec/payload",
                      json=SAMPLE_PAYLOAD)
        # Solo necesita email y FCM
        responses.add(responses.POST, f"{base}/worker/invoice/inv-rec/send-email",
                      json={"status": "ok", "message_id": "msg-1"})
        responses.add(responses.POST, f"{base}/worker/invoice/inv-rec/send-fcm",
                      json={"status": "ok", "sent": 1})

        worker._process({"invoice_id": "inv-rec"})

        # No debe haber importado ni renderizado (ya estaba hecho)
        assert len(gestor.facturas) == 0
        assert len(renderer.calls) == 0

        # Pero si pidio email y FCM
        api_paths = [c.request.path_url for c in responses.calls]
        assert any("/send-email" in p for p in api_paths)
        assert any("/send-fcm" in p for p in api_paths)

    @responses.activate
    def test_error_reported_on_failure(self, tmp_path):
        config = _make_config(tmp_path)
        gestor = MockGestor()
        worker = InvoiceWorker(config, gestor=gestor)

        base = config.api_base_url

        # Status
        responses.add(responses.GET, f"{base}/worker/invoice/inv-err/status",
                      json={})
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


class TestGracefulShutdown:
    def test_stop_sets_running_false(self, tmp_path):
        config = _make_config(tmp_path)
        worker = InvoiceWorker(config)

        assert worker._running is True
        worker.stop(signum=15)
        assert worker._running is False

    def test_sleep_respects_stop(self, tmp_path):
        config = _make_config(tmp_path)
        worker = InvoiceWorker(config)

        import time
        worker._running = False
        start = time.monotonic()
        worker._sleep(10)  # Deberia salir inmediatamente
        elapsed = time.monotonic() - start
        assert elapsed < 2  # Mucho menos de 10s


class TestBackoff:
    @responses.activate
    def test_consecutive_errors_increase_backoff(self, tmp_path):
        config = _make_config(tmp_path)
        worker = InvoiceWorker(config)

        # Simular errores consecutivos
        assert worker._consecutive_errors == 0
        worker._consecutive_errors = 3
        # Backoff seria poll_interval * 2^3 = 5 * 8 = 40
        expected = min(5 * (2 ** 3), 300)
        assert expected == 40
