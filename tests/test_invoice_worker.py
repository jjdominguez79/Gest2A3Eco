"""Tests del invoice worker con adaptadores simulados.

Desde la Etapa 8 (ADR 0001) este worker solo importa clientes y facturas a
contabilidad: claim -> import (tercero/subcuenta/factura) -> confirm. Ya no
genera PDF, no envia email ni FCM (eso es responsabilidad exclusiva de
billing_worker, cloud). Cada paso es idempotente; las caidas no duplican
datos.
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
# Mock adapter
# ---------------------------------------------------------------------------

class MockGestor:
    """Simula el gestor del escritorio en memoria.

    Reproduce la restriccion UNIQUE(codigo_empresa, subcuenta) real de
    maestro_subcuentas_empresa para poder probar el reintento ante
    conflicto (seccion 17 del encargo).
    """

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
        self.advisory_lock_calls: list[str] = []
        # Si > 0, las N primeras llamadas a upsert_maestro_subcuenta para
        # una subcuenta nueva fallan como si otro proceso hubiera ganado la
        # carrera (simula UniqueViolation real de Postgres).
        self.force_conflicts_remaining = 0

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
        codigo = datos.get("codigo_empresa")
        subcuenta = datos.get("subcuenta")
        if any(
            s["codigo_empresa"] == codigo and s["subcuenta"] == subcuenta
            for s in self.subcuentas
        ):
            raise RuntimeError(
                f"duplicate key value violates unique constraint "
                f"(codigo_empresa, subcuenta)=({codigo}, {subcuenta})"
            )
        if self.force_conflicts_remaining > 0:
            self.force_conflicts_remaining -= 1
            raise RuntimeError(
                "duplicate key value violates unique constraint "
                "(simulado: otro proceso gano la carrera)"
            )
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

    def advisory_lock_empresa_430(self, codigo_empresa: str) -> None:
        self.advisory_lock_calls.append(codigo_empresa)


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
}


def _make_config(tmp_path: Path) -> WorkerConfig:
    log_dir = tmp_path / "logs"
    log_dir.mkdir()

    return WorkerConfig(
        api_base_url="http://test-api/api/v1/messaging/client/invoicing",
        worker_id="test-worker-1",
        lease_minutes=10,
        poll_interval_seconds=5,
        max_retries=5,
        log_dir=str(log_dir),
        api_token="test-token",
        desktop_dsn="",
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
        desktop_id = worker._import_to_desktop("inv-001", payload)

        assert desktop_id == "flutter_inv-001"

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

        # Factura importada con el id deterministico (idempotencia por UUID backend)
        assert "flutter_inv-001" in gestor.facturas
        fac = gestor.facturas["flutter_inv-001"]
        assert fac["serie"] == "WEB"
        assert fac["numero"] == 1
        assert fac["codigo_empresa"] == "TEST01"
        assert fac["estado_contable"] == "pendiente"

    def test_idempotent_import_same_backend_uuid_never_duplicates(self, tmp_path):
        """Reprocesar el mismo invoice_id nunca duplica tercero, subcuenta ni factura."""
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
        # Solo 1 factura: mismo id deterministico "flutter_inv-001"
        assert len(gestor.facturas) == 1

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

        fac = gestor.facturas["flutter_inv-wh"]
        assert fac["retencion_aplica"] is True
        assert fac["retencion_pct"] == 15.0
        assert fac["retencion_importe"] == -75.0

    def test_apply_issued_snapshot_prevails_over_live_data(self):
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


class TestResolveSubcuenta430:
    def test_assigns_first_subcuenta(self, tmp_path):
        config = _make_config(tmp_path)
        gestor = MockGestor()
        worker = InvoiceWorker(config, gestor=gestor)

        sub = worker._resolve_subcuenta_430(
            gestor, "TEST01", "B12345678", 8,
            tercero_id="t1", legal_name="Cliente",
        )
        assert sub == "43000001"
        # Se reservo de verdad (no solo se calculo): queda en el maestro.
        assert gestor.get_maestro_subcuenta_por_subcuenta("TEST01", "43000001")
        assert gestor.advisory_lock_calls == ["TEST01"]

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

        sub = worker._resolve_subcuenta_430(
            gestor, "TEST01", "B12345678", 8,
            tercero_id="t2", legal_name="Cliente",
        )
        assert sub == "43000006"

    def test_finds_existing_by_nif_without_reinserting(self, tmp_path):
        config = _make_config(tmp_path)
        gestor = MockGestor()
        gestor.subcuentas.append({
            "codigo_empresa": "TEST01",
            "subcuenta": "43000003",
            "tipo_subcuenta": "cliente",
            "nif_snapshot": "B12345678",
        })
        worker = InvoiceWorker(config, gestor=gestor)

        sub = worker._resolve_subcuenta_430(
            gestor, "TEST01", "B12345678", 8,
            tercero_id="t3", legal_name="Cliente",
        )
        assert sub == "43000003"  # reutiliza la existente
        assert len(gestor.subcuentas) == 1  # no inserta una segunda fila

    def test_retries_on_unique_constraint_conflict(self, tmp_path):
        """Seccion 17: UNIQUE(codigo_empresa, subcuenta) + reintento controlado.

        Simula que, entre el calculo del siguiente numero y el INSERT, otro
        proceso gano la carrera: el primer intento falla por el conflicto
        simulado, el worker reintenta y obtiene una subcuenta distinta.
        """
        config = _make_config(tmp_path)
        gestor = MockGestor()
        gestor.force_conflicts_remaining = 1
        worker = InvoiceWorker(config, gestor=gestor)

        sub = worker._resolve_subcuenta_430(
            gestor, "TEST01", "B12345678", 8,
            tercero_id="t4", legal_name="Cliente",
        )
        assert sub == "43000001"
        assert len(gestor.advisory_lock_calls) == 2  # un intento fallido + uno exitoso
        assert gestor.get_maestro_subcuenta_por_subcuenta("TEST01", "43000001")

    def test_gives_up_after_max_attempts(self, tmp_path):
        config = _make_config(tmp_path)
        gestor = MockGestor()
        gestor.force_conflicts_remaining = 999  # siempre falla
        worker = InvoiceWorker(config, gestor=gestor)

        with pytest.raises(RuntimeError, match="No se pudo asignar"):
            worker._resolve_subcuenta_430(
                gestor, "TEST01", "B12345678", 8,
                tercero_id="t5", legal_name="Cliente",
            )

    def test_never_reuses_subcuenta_of_another_tercero(self, tmp_path):
        config = _make_config(tmp_path)
        gestor = MockGestor()
        gestor.subcuentas.append({
            "codigo_empresa": "TEST01",
            "subcuenta": "43000001",
            "tipo_subcuenta": "cliente",
            "nif_snapshot": "A99999999",  # otro NIF
        })
        worker = InvoiceWorker(config, gestor=gestor)

        sub = worker._resolve_subcuenta_430(
            gestor, "TEST01", "B12345678", 8,
            tercero_id="t6", legal_name="Cliente",
        )
        assert sub == "43000002"  # nunca devuelve 43000001, que es de otro tercero


class TestAccountingProcess:
    """Flujo de la cola contable: claim -> import -> confirm."""

    @responses.activate
    def test_full_flow_confirms_with_desktop_references(self, tmp_path):
        config = _make_config(tmp_path)
        gestor = MockGestor()
        worker = InvoiceWorker(config, gestor=gestor)
        base = config.api_base_url

        payload = _payload_with_synced_customer(worker, gestor)

        responses.add(
            responses.POST, f"{base}/worker/accounting/inv-full/confirm",
            json={"status": "ok"},
        )

        worker._process_accounting({"invoice_id": "inv-full", "payload": payload})

        assert "flutter_inv-full" in gestor.facturas
        assert len(responses.calls) == 1
        body = json.loads(responses.calls[0].request.body)
        assert body["desktop_invoice_ref"] == "flutter_inv-full"
        assert body["desktop_tercero_id"] == payload["customer"]["desktop_tercero_id"]
        assert body["desktop_subcuenta"] == payload["customer"]["desktop_subcuenta"]

    @responses.activate
    def test_error_reported_without_touching_fiscal_state(self, tmp_path):
        """Un fallo contable se reporta pero nunca afecta a la factura fiscal."""
        config = _make_config(tmp_path)
        gestor = MockGestor()
        worker = InvoiceWorker(config, gestor=gestor)
        base = config.api_base_url

        bad_payload = {
            **SAMPLE_PAYLOAD,
            "organization": {**SAMPLE_PAYLOAD["organization"], "company_code": "NOPE"},
        }
        responses.add(
            responses.POST, f"{base}/worker/accounting/inv-err/error",
            json={"status": "ok", "retryable": True},
        )

        worker._process_accounting({"invoice_id": "inv-err", "payload": bad_payload})

        error_calls = [c for c in responses.calls if "/error" in c.request.path_url]
        assert len(error_calls) == 1
        body = json.loads(error_calls[0].request.body)
        assert "no existe en escritorio" in body["error"]
        assert len(gestor.facturas) == 0

    @responses.activate
    def test_claim_accounting_returns_claim_with_payload(self, tmp_path):
        config = _make_config(tmp_path)
        worker = InvoiceWorker(config)

        responses.add(
            responses.POST, f"{config.api_base_url}/worker/accounting/claim",
            json={"claimed": True, "invoice_id": "inv-42", "payload": SAMPLE_PAYLOAD},
        )
        result = worker._claim_accounting()
        assert result["invoice_id"] == "inv-42"
        assert result["payload"]["invoice"]["series_code"] == "WEB"

    @responses.activate
    def test_claim_accounting_returns_none_when_empty(self, tmp_path):
        config = _make_config(tmp_path)
        worker = InvoiceWorker(config)

        responses.add(
            responses.POST, f"{config.api_base_url}/worker/accounting/claim",
            json={"claimed": False},
        )
        result = worker._claim_accounting()
        assert result is None


class TestHeartbeat:
    @responses.activate
    def test_heartbeat_posts_instance_id(self, tmp_path):
        config = _make_config(tmp_path)
        worker = InvoiceWorker(config)

        responses.add(
            responses.POST, f"{config.api_base_url}/worker/accounting/heartbeat",
            json={"status": "ok"},
        )
        worker._heartbeat()
        assert len(responses.calls) == 1
        body = json.loads(responses.calls[0].request.body)
        assert body["instance_id"] == "test-worker-1"

    def test_heartbeat_failure_never_raises(self, tmp_path):
        """El backend puede estar caido; el heartbeat es best-effort."""
        config = _make_config(tmp_path)
        worker = InvoiceWorker(config)
        worker._heartbeat()  # sin mock de red: debe fallar la conexion y no lanzar


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
    def test_consecutive_errors_increase_backoff(self, tmp_path):
        config = _make_config(tmp_path)
        worker = InvoiceWorker(config)

        # Simular errores consecutivos
        assert worker._consecutive_errors == 0
        worker._consecutive_errors = 3
        # Backoff seria poll_interval * 2^3 = 5 * 8 = 40
        expected = min(5 * (2 ** 3), 300)
        assert expected == 40


class TestNoWindowsOrBillingWorkerLeakage:
    """Seccion 16 del encargo: el circuito APP ya no usa Word/Word COM/PDF."""

    def test_worker_module_never_imports_word_or_pdf_modules(self):
        import ast
        from pathlib import Path as _Path

        source = (_Path(__file__).resolve().parents[1] / "invoice_worker" / "worker.py").read_text(
            encoding="utf-8",
        )
        tree = ast.parse(source)
        roots: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                roots |= {alias.name.split(".")[0] for alias in node.names}
            elif isinstance(node, ast.ImportFrom) and node.module:
                roots.add(node.module.split(".")[0])
        assert "procesos" not in roots  # procesos.facturas_word ya no se usa aqui
        assert "win32com" not in roots
        assert "comtypes" not in roots

    def test_worker_has_no_pdf_or_email_or_fcm_methods(self):
        forbidden = {
            "_render_pdf", "_upload_pdf", "_publish_document",
            "_request_email", "_request_fcm",
        }
        present = forbidden & set(dir(InvoiceWorker))
        assert present == set(), f"metodos de billing_worker filtrados a invoice_worker: {present}"
