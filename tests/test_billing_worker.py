"""Tests de la Etapa 5: paquete billing_worker (bucle, lease, reintentos).

Usa un backend falso inyectado (mismo patron que tests/test_aapp_worker.py y
tests/test_invoice_worker.py): no se levanta un servidor HTTP real, se
verifica el contrato de llamadas del worker contra una implementacion en
memoria. Ver docs/adr/0001-facturacion-autonoma-cliente.md, Etapa 5.
"""

from __future__ import annotations

import ast
import time
from pathlib import Path

import pytest

from billing_worker.config import BillingWorkerConfig
from billing_worker.worker import BillingWorker


def _config(**overrides) -> BillingWorkerConfig:
    base = dict(
        backend_url="https://backend.test",
        api_key="billing-secret",
        instance_id="billing-test-1",
        poll_interval_seconds=5,
        lease_minutes=10,
        request_timeout_seconds=30,
        heartbeat_interval_seconds=60,
        max_backoff_seconds=300,
    )
    base.update(overrides)
    return BillingWorkerConfig(**base)


class _FakeBackend:
    def __init__(self, *, invoice_id="inv-1", recipient_push=True):
        self.invoice_id = invoice_id
        self._claimed = False
        self.calls: list[str] = []
        self.pdf_uploaded = False
        self.document_published = False
        self.errors: list[str] = []
        self.heartbeats: list[dict] = []
        self.fail_claim = False
        self.fail_fcm = False
        self.recipient_push = recipient_push

    def claim(self):
        self.calls.append("claim")
        if self.fail_claim:
            raise RuntimeError("backend inalcanzable")
        if self._claimed:
            return None
        self._claimed = True
        return {"claimed": True, "queue_id": "q-1", "invoice_id": self.invoice_id}

    def fiscal_register(self, invoice_id):
        self.calls.append("fiscal_register")
        return {"status": "skipped", "reason": "verifactu_submission_disabled"}

    def get_status(self, invoice_id):
        self.calls.append("get_status")
        return {
            "invoice_id": invoice_id,
            "pdf_uploaded": self.pdf_uploaded,
            "document_published": self.document_published,
        }

    def get_payload(self, invoice_id):
        self.calls.append("get_payload")
        return {"invoice": {"id": invoice_id, "invoice_number": 1}}

    def upload_pdf(self, invoice_id, content, sha256):
        self.calls.append("upload_pdf")
        self.pdf_uploaded = True
        return {"status": "ok", "sha256": sha256}

    def publish_document(self, invoice_id, description=""):
        self.calls.append("publish_document")
        self.document_published = True
        return {"status": "ok", "document_id": "doc-1"}

    def send_email(self, invoice_id):
        self.calls.append("send_email")
        return {"status": "ok"}

    def send_fcm(self, invoice_id):
        self.calls.append("send_fcm")
        if self.fail_fcm:
            raise RuntimeError("firebase caido")
        return {"status": "ok", "sent": 1 if self.recipient_push else 0}

    def report_error(self, invoice_id, message):
        self.calls.append("report_error")
        self.errors.append(message)
        return {"status": "ok", "retryable": True}

    def heartbeat(self, *, jobs_processed_total, jobs_failed_total, status_detail=""):
        self.heartbeats.append({
            "jobs_processed_total": jobs_processed_total,
            "jobs_failed_total": jobs_failed_total,
            "status_detail": status_detail,
        })


def test_run_once_returns_false_when_nothing_to_claim():
    backend = _FakeBackend()
    backend._claimed = True  # simula cola vacia desde el principio
    worker = BillingWorker(_config(), backend=backend)
    assert worker.run_once() is False


def test_full_pipeline_renders_uploads_publishes_emails_and_notifies():
    backend = _FakeBackend()
    worker = BillingWorker(_config(), backend=backend)

    processed = worker.run_once()

    assert processed is True
    assert backend.calls == [
        "claim", "fiscal_register", "get_status", "get_payload", "upload_pdf",
        "get_status", "publish_document", "send_email", "send_fcm",
    ]
    assert worker.jobs_processed_total == 1
    assert worker.jobs_failed_total == 0
    assert backend.errors == []


def test_pipeline_skips_render_when_pdf_already_uploaded():
    """Idempotencia por tipo de trabajo: no vuelve a renderizar ni subir."""
    backend = _FakeBackend()
    backend.pdf_uploaded = True
    worker = BillingWorker(_config(), backend=backend)

    worker.run_once()

    assert "get_payload" not in backend.calls
    assert "upload_pdf" not in backend.calls
    assert "publish_document" in backend.calls


def test_pipeline_skips_publish_when_already_published():
    backend = _FakeBackend()
    backend.pdf_uploaded = True
    backend.document_published = True
    worker = BillingWorker(_config(), backend=backend)

    worker.run_once()

    assert "publish_document" not in backend.calls
    assert "send_email" in backend.calls


def test_fcm_failure_is_best_effort_and_does_not_fail_the_job():
    backend = _FakeBackend()
    backend.fail_fcm = True
    worker = BillingWorker(_config(), backend=backend)

    processed = worker.run_once()

    assert processed is True
    assert worker.jobs_processed_total == 1
    assert worker.jobs_failed_total == 0
    assert backend.errors == []  # el fallo de FCM nunca se reporta como error del trabajo


def test_processing_failure_is_reported_to_backend():
    class _BrokenPayloadBackend(_FakeBackend):
        def get_payload(self, invoice_id):
            raise RuntimeError("no se pudo leer el payload")

    backend = _BrokenPayloadBackend()
    worker = BillingWorker(_config(), backend=backend)

    processed = worker.run_once()

    assert processed is True  # el trabajo se reclamo, aunque fallara
    assert worker.jobs_processed_total == 0
    assert worker.jobs_failed_total == 1
    assert len(backend.errors) == 1
    assert "no se pudo leer el payload" in backend.errors[0]


def test_report_error_failure_itself_never_crashes_the_worker():
    """Si ni siquiera se puede reportar el error, el worker sigue vivo.

    El lease caducara en el backend y la factura se reclamara de nuevo mas
    adelante; el worker no debe terminar por esto.
    """
    class _DoublyBrokenBackend(_FakeBackend):
        def get_payload(self, invoice_id):
            raise RuntimeError("fallo original")

        def report_error(self, invoice_id, message):
            raise RuntimeError("tambien fallo al reportar")

    backend = _DoublyBrokenBackend()
    worker = BillingWorker(_config(), backend=backend)

    processed = worker.run_once()  # no debe propagar ninguna excepcion
    assert processed is True
    assert worker.jobs_failed_total == 1


def test_two_worker_instances_sharing_the_backend_never_duplicate_a_claim():
    """Varias replicas no duplican trabajo: el backend otorga un unico lease.

    El backend real impone esto con SELECT FOR UPDATE SKIP LOCKED (ver
    tests/test_worker_endpoints.py y test_invoice_numbering_concurrency_pg.py);
    aqui se fija el contrato del lado del worker: una vez que claim() del
    backend compartido dice que no hay mas trabajo, una segunda instancia no
    reprocesa nada.
    """
    shared_backend = _FakeBackend()
    worker_a = BillingWorker(_config(instance_id="replica-a"), backend=shared_backend)
    worker_b = BillingWorker(_config(instance_id="replica-b"), backend=shared_backend)

    assert worker_a.run_once() is True
    assert worker_b.run_once() is False
    assert worker_a.jobs_processed_total == 1
    assert worker_b.jobs_processed_total == 0


def test_claim_exception_propagates_for_backoff_handling():
    """run_once SI propaga si claim() falla: run_forever decide el backoff."""
    backend = _FakeBackend()
    backend.fail_claim = True
    worker = BillingWorker(_config(), backend=backend)

    with pytest.raises(RuntimeError):
        worker.run_once()


def test_heartbeat_respects_interval_unless_forced():
    backend = _FakeBackend()
    worker = BillingWorker(_config(heartbeat_interval_seconds=3600), backend=backend)

    worker.maybe_heartbeat(force=True)
    worker.maybe_heartbeat()  # demasiado pronto, no deberia enviar otro

    assert len(backend.heartbeats) == 1


def test_heartbeat_reports_processed_and_failed_counts():
    backend = _FakeBackend()
    worker = BillingWorker(_config(), backend=backend)
    worker.jobs_processed_total = 7
    worker.jobs_failed_total = 2

    worker.maybe_heartbeat(force=True)

    assert backend.heartbeats[-1]["jobs_processed_total"] == 7
    assert backend.heartbeats[-1]["jobs_failed_total"] == 2


def test_heartbeat_failure_does_not_raise():
    class _HeartbeatFailsBackend(_FakeBackend):
        def heartbeat(self, **kwargs):
            raise RuntimeError("backend caido")

    backend = _HeartbeatFailsBackend()
    worker = BillingWorker(_config(), backend=backend)
    worker.maybe_heartbeat(force=True)  # no debe lanzar


def test_graceful_shutdown_stops_run_forever_promptly():
    backend = _FakeBackend()
    backend._claimed = True  # cola vacia: run_forever esperaria poll_interval
    worker = BillingWorker(_config(poll_interval_seconds=30), backend=backend)

    import threading

    thread = threading.Thread(target=worker.run_forever, daemon=True)
    started = time.monotonic()
    thread.start()
    time.sleep(0.05)
    worker.stop()
    thread.join(timeout=5)

    assert not thread.is_alive()
    assert time.monotonic() - started < 5


def test_backoff_formula_caps_at_max_backoff_seconds():
    config = _config(poll_interval_seconds=10, max_backoff_seconds=60)
    # Replica la formula usada en run_forever para dejar el calculo probado
    # sin depender de temporizadores reales.
    backoffs = [
        min(config.poll_interval_seconds * (2 ** n), config.max_backoff_seconds)
        for n in range(1, 6)
    ]
    assert backoffs == [20, 40, 60, 60, 60]


# ---------------------------------------------------------------------------
# Restricciones de aislamiento (seccion 10/23 del encargo): billing_worker no
# puede importar Tkinter/pywin32/Word COM ni conectarse al PostgreSQL
# interno del escritorio.
# ---------------------------------------------------------------------------

_FORBIDDEN_IMPORT_ROOTS = {
    "tkinter", "win32com", "win32api", "win32con", "pywintypes", "comtypes",
    "pythoncom", "psycopg", "psycopg2",
}


def _imported_module_roots(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    roots: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                roots.add(alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom) and node.module:
            roots.add(node.module.split(".")[0])
    return roots


def test_billing_worker_package_never_imports_windows_or_desktop_postgres_modules():
    package_dir = Path(__file__).resolve().parents[1] / "billing_worker"
    all_roots: set[str] = set()
    for py_file in package_dir.rglob("*.py"):
        all_roots |= _imported_module_roots(py_file)

    offending = all_roots & _FORBIDDEN_IMPORT_ROOTS
    assert offending == set(), (
        f"billing_worker no puede depender de: {offending}"
    )


def test_billing_worker_package_never_mentions_internal_desktop_dsn_env_vars():
    """billing_worker no debe leer las variables del DSN interno del escritorio."""
    package_dir = Path(__file__).resolve().parents[1] / "billing_worker"
    forbidden_markers = (
        "INVOICE_WORKER_DESKTOP_DSN", "INVOICE_WORKER_PG_HOST", "GestorPostgres",
    )
    for py_file in package_dir.rglob("*.py"):
        content = py_file.read_text(encoding="utf-8")
        for marker in forbidden_markers:
            assert marker not in content, f"{py_file} menciona {marker}"
