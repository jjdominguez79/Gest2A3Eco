from __future__ import annotations

import argparse
import hashlib
import re
import sys
import uuid
from contextlib import suppress
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any


BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

BACKEND_IMPORT_ERROR: ModuleNotFoundError | None = None

try:
    from fastapi.testclient import TestClient
    from sqlalchemy.orm import Session

    from app.db.session import SessionLocal
    from app.main import app
    from app.models.accounting_batch import AccountingBatch
    from app.models.accounting_batch_item import AccountingBatchItem
    from app.models.company import Company
    from app.models.company_account import CompanyAccount
    from app.models.company_membership import CompanyMembership, CompanyRole
    from app.models.document import Document
    from app.models.document_event import DocumentEvent
    from app.models.enums import (
        A3ImportMode,
        AccountSource,
        AccountSyncStatus,
        AccountType,
        DocumentSource,
        DocumentType,
        DocumentWorkflowStatus,
        InvoiceReviewStatus,
        ThirdPartyType,
    )
    from app.models.global_third_party import GlobalThirdParty
    from app.models.invoice_review import InvoiceReview
    from app.models.user import User
    from app.services.security_service import hash_password
except ModuleNotFoundError as exc:  # pragma: no cover - depends on local env
    BACKEND_IMPORT_ERROR = exc
    SessionLocal = None
    TestClient = Any
    Session = Any


SMOKE_USER_EMAIL = "smoke.phase6@gestinem.local"
SMOKE_USER_PASSWORD = "GestinemSmoke6!"
SMOKE_USER_NAME = "Smoke Phase 6 Admin"
SMOKE_COMPANY_NAME = "Gestinem Smoke Phase 6"
SMOKE_COMPANY_CIF = "SMKPHASE6001"
SMOKE_SUPPLIER_NAME = "SMOKE PHASE 6 SUPPLIER SL"
SMOKE_SUPPLIER_TAX_ID = "B12345678"


class SmokeFailure(RuntimeError):
    pass


@dataclass
class SmokeContext:
    run_id: str
    cleanup: bool
    db: Session
    client: TestClient
    created_document_ids: list[uuid.UUID] = field(default_factory=list)
    created_batch_ids: list[uuid.UUID] = field(default_factory=list)
    created_paths: list[Path] = field(default_factory=list)
    user: User | None = None
    company: Company | None = None
    supplier: GlobalThirdParty | None = None
    supplier_account: CompanyAccount | None = None
    document: Document | None = None
    invoice_review: InvoiceReview | None = None
    token: str | None = None
    batch_id: uuid.UUID | None = None

    @property
    def auth_headers(self) -> dict[str, str]:
        if self.company is None or self.token is None:
            raise RuntimeError("Smoke context is not authenticated.")
        return {
            "Authorization": f"Bearer {self.token}",
            "X-Company-Id": str(self.company.id),
        }


class Reporter:
    def __init__(self) -> None:
        self._ok_count = 0

    def ok(self, message: str) -> None:
        self._ok_count += 1
        print(f"[OK] {message}")

    def fail(self, *, stage: str, message: str, expected: str, actual: str) -> None:
        print(f"[FAIL] {stage}: {message}")
        print(f"       expected: {expected}")
        print(f"       actual:   {actual}")
        raise SmokeFailure(f"{stage}: {message}")

    def assert_true(self, condition: bool, *, stage: str, message: str, expected: str, actual: str) -> None:
        if not condition:
            self.fail(stage=stage, message=message, expected=expected, actual=actual)
        self.ok(message)

    @property
    def ok_count(self) -> int:
        return self._ok_count


def main() -> int:
    if BACKEND_IMPORT_ERROR is not None:
        print("[FAIL] preflight: no se pudo cargar el backend para el smoke test")
        print("       expected: dependencias backend instaladas, incluyendo psycopg[binary]")
        print(f"       actual:   {BACKEND_IMPORT_ERROR}")
        print("\nInstala dependencias con:")
        print(r"python -m pip install -r c:\Users\GestinemFiscal\Gest2A3Eco\gestinemappfull\backend\requirements.txt")
        return 2

    parser = argparse.ArgumentParser(description="Smoke test extremo a extremo de la Fase 6.")
    parser.add_argument(
        "--cleanup",
        action="store_true",
        help="Elimina batch/documento de prueba creados en esta ejecución al finalizar.",
    )
    args = parser.parse_args()

    run_id = datetime.now(UTC).strftime("%Y%m%d%H%M%S")
    reporter = Reporter()

    with SessionLocal() as db:
        with TestClient(app) as client:
            ctx = SmokeContext(
                run_id=run_id,
                cleanup=args.cleanup,
                db=db,
                client=client,
            )
            try:
                prepare_seed_data(ctx, reporter)
                authenticate(ctx, reporter)
                configure_company_a3(ctx, reporter)
                validate_pending_documents(ctx, reporter)
                create_batch(ctx, reporter)
                generate_batch(ctx, reporter)
                download_batch(ctx, reporter)
                mark_batch_exported(ctx, reporter)
                validate_traceability(ctx, reporter)
                print(f"\nSmoke test Phase 6 completado con {reporter.ok_count} comprobaciones OK.")
                return 0
            except SmokeFailure:
                return 1
            finally:
                if args.cleanup:
                    cleanup_run(ctx)


def prepare_seed_data(ctx: SmokeContext, reporter: Reporter) -> None:
    user = ctx.db.query(User).filter(User.email == SMOKE_USER_EMAIL).first()
    if user is None:
        user = User(
            email=SMOKE_USER_EMAIL,
            full_name=SMOKE_USER_NAME,
            password_hash=hash_password(SMOKE_USER_PASSWORD),
            is_active=True,
            is_superuser=False,
        )
        ctx.db.add(user)
        ctx.db.flush()
    else:
        user.password_hash = hash_password(SMOKE_USER_PASSWORD)
        user.is_active = True
        user.full_name = SMOKE_USER_NAME

    company = ctx.db.query(Company).filter(Company.name == SMOKE_COMPANY_NAME).first()
    if company is None:
        company = Company(
            name=SMOKE_COMPANY_NAME,
            cif=SMOKE_COMPANY_CIF,
            is_active=True,
        )
        ctx.db.add(company)
        ctx.db.flush()

    membership = (
        ctx.db.query(CompanyMembership)
        .filter(
            CompanyMembership.company_id == company.id,
            CompanyMembership.user_id == user.id,
        )
        .first()
    )
    if membership is None:
        membership = CompanyMembership(
            company_id=company.id,
            user_id=user.id,
            role=CompanyRole.ADMIN,
            is_active=True,
        )
        ctx.db.add(membership)
    else:
        membership.role = CompanyRole.ADMIN
        membership.is_active = True

    supplier = (
        ctx.db.query(GlobalThirdParty)
        .filter(
            GlobalThirdParty.tax_id == SMOKE_SUPPLIER_TAX_ID,
            GlobalThirdParty.legal_name == SMOKE_SUPPLIER_NAME,
        )
        .first()
    )
    if supplier is None:
        supplier = GlobalThirdParty(
            third_party_type=ThirdPartyType.SUPPLIER,
            tax_id=SMOKE_SUPPLIER_TAX_ID,
            legal_name=SMOKE_SUPPLIER_NAME,
            is_active=True,
        )
        ctx.db.add(supplier)
        ctx.db.flush()

    supplier_account = (
        ctx.db.query(CompanyAccount)
        .filter(
            CompanyAccount.company_id == company.id,
            CompanyAccount.global_third_party_id == supplier.id,
            CompanyAccount.account_type == AccountType.SUPPLIER,
        )
        .first()
    )
    if supplier_account is None:
        supplier_account = CompanyAccount(
            company_id=company.id,
            account_code="400900000001",
            name=SMOKE_SUPPLIER_NAME,
            account_type=AccountType.SUPPLIER,
            global_third_party_id=supplier.id,
            tax_id=SMOKE_SUPPLIER_TAX_ID,
            legal_name=SMOKE_SUPPLIER_NAME,
            source=AccountSource.MANUAL_APP,
            sync_status=AccountSyncStatus.PENDING_SYNC,
            is_active=True,
        )
        ctx.db.add(supplier_account)
        ctx.db.flush()

    document = _create_pending_accounting_document(ctx, user=user, company=company, supplier=supplier, supplier_account=supplier_account)

    ctx.db.commit()
    ctx.user = user
    ctx.company = company
    ctx.supplier = supplier
    ctx.supplier_account = supplier_account
    ctx.document = document
    ctx.invoice_review = document.invoice_review

    reporter.ok("empresa de prueba y datos base listos")


def authenticate(ctx: SmokeContext, reporter: Reporter) -> None:
    response = ctx.client.post(
        "/api/v1/auth/login",
        json={"email": SMOKE_USER_EMAIL, "password": SMOKE_USER_PASSWORD},
    )
    if response.status_code != 200:
        raise SmokeFailure(f"auth login failed: {response.status_code} {response.text}")
    payload = response.json()
    ctx.token = payload["access_token"]
    reporter.ok("login JWT obtenido para usuario administrador de prueba")


def configure_company_a3(ctx: SmokeContext, reporter: Reporter) -> None:
    assert ctx.company is not None
    a3_code = _company_code_for(ctx.company.id)
    put_response = ctx.client.put(
        f"/api/v1/companies/{ctx.company.id}/a3-settings",
        headers=ctx.auth_headers,
        json={
            "a3_enabled": True,
            "a3_company_code": a3_code,
            "a3_export_path": r"\\SMOKE\A3\IMPORT",
            "a3_import_mode": A3ImportMode.MANUAL.value,
        },
    )
    if put_response.status_code != 200:
        raise SmokeFailure(f"a3 settings update failed: {put_response.status_code} {put_response.text}")
    payload = put_response.json()
    reporter.assert_true(
        payload["a3_enabled"] is True,
        stage="empresa",
        message="empresa A3 configurada",
        expected="a3_enabled=true",
        actual=str(payload["a3_enabled"]),
    )
    reporter.assert_true(
        payload["a3_company_code"] == a3_code,
        stage="empresa",
        message="codigo A3 guardado",
        expected=a3_code,
        actual=str(payload["a3_company_code"]),
    )
    reporter.assert_true(
        payload["a3_import_mode"] == A3ImportMode.MANUAL.value,
        stage="empresa",
        message="modo de importacion A3 guardado",
        expected=A3ImportMode.MANUAL.value,
        actual=str(payload["a3_import_mode"]),
    )


def validate_pending_documents(ctx: SmokeContext, reporter: Reporter) -> None:
    assert ctx.document is not None
    response = ctx.client.get(
        "/api/v1/accounting/documents/pending",
        headers=ctx.auth_headers,
    )
    if response.status_code != 200:
        raise SmokeFailure(f"pending documents failed: {response.status_code} {response.text}")
    payload = response.json()
    document_row = next((item for item in payload if item["document_id"] == str(ctx.document.id)), None)
    reporter.assert_true(
        document_row is not None,
        stage="documentos",
        message="documentos pendientes encontrados",
        expected=f"documento {ctx.document.id} presente en pending_accounting",
        actual=f"ids devueltos: {[item['document_id'] for item in payload]}",
    )


def create_batch(ctx: SmokeContext, reporter: Reporter) -> None:
    assert ctx.document is not None
    response = ctx.client.post(
        "/api/v1/accounting/batches",
        headers=ctx.auth_headers,
        json={
            "document_ids": [str(ctx.document.id)],
            "notes": f"smoke test phase6 draft {ctx.run_id}",
        },
    )
    if response.status_code != 200:
        raise SmokeFailure(f"batch create failed: {response.status_code} {response.text}")
    payload = response.json()
    ctx.batch_id = uuid.UUID(payload["id"])
    ctx.created_batch_ids.append(ctx.batch_id)
    reporter.assert_true(
        payload["status"] == "draft",
        stage="batch",
        message="lote creado",
        expected="draft",
        actual=str(payload["status"]),
    )


def generate_batch(ctx: SmokeContext, reporter: Reporter) -> None:
    assert ctx.batch_id is not None
    assert ctx.document is not None
    response = ctx.client.post(
        f"/api/v1/accounting/batches/{ctx.batch_id}/generate",
        headers=ctx.auth_headers,
        json={"notes": f"smoke test phase6 generated {ctx.run_id}"},
    )
    if response.status_code != 200:
        raise SmokeFailure(f"batch generate failed: {response.status_code} {response.text}")
    payload = response.json()
    reporter.assert_true(
        payload["status"] == "generated",
        stage="batch",
        message="lote generado",
        expected="generated",
        actual=str(payload["status"]),
    )

    ctx.db.refresh(ctx.document)
    reporter.assert_true(
        ctx.document.workflow_status == DocumentWorkflowStatus.BATCHED,
        stage="documentos",
        message="documentos pasan a batched al generar lote",
        expected=DocumentWorkflowStatus.BATCHED.value,
        actual=ctx.document.workflow_status.value,
    )


def download_batch(ctx: SmokeContext, reporter: Reporter) -> None:
    assert ctx.batch_id is not None
    response = ctx.client.post(
        f"/api/v1/accounting/batches/{ctx.batch_id}/download",
        headers=ctx.auth_headers,
    )
    if response.status_code != 200:
        raise SmokeFailure(f"batch download failed: {response.status_code} {response.text}")

    detail = ctx.client.get(
        f"/api/v1/accounting/batches/{ctx.batch_id}",
        headers=ctx.auth_headers,
    )
    if detail.status_code != 200:
        raise SmokeFailure(f"batch detail after download failed: {detail.status_code} {detail.text}")
    payload = detail.json()

    reporter.assert_true(
        payload["status"] == "downloaded",
        stage="batch",
        message="lote descargado",
        expected="downloaded",
        actual=str(payload["status"]),
    )
    reporter.assert_true(
        len(response.content) > 0,
        stage="archivo",
        message="archivo .dat disponible para descarga",
        expected="bytes > 0",
        actual=str(len(response.content)),
    )


def mark_batch_exported(ctx: SmokeContext, reporter: Reporter) -> None:
    assert ctx.batch_id is not None
    assert ctx.document is not None
    response = ctx.client.post(
        f"/api/v1/accounting/batches/{ctx.batch_id}/mark-exported",
        headers=ctx.auth_headers,
        json={"notes": f"smoke test phase6 exported {ctx.run_id}"},
    )
    if response.status_code != 200:
        raise SmokeFailure(f"batch export failed: {response.status_code} {response.text}")
    payload = response.json()
    reporter.assert_true(
        payload["status"] == "exported",
        stage="batch",
        message="lote exportado",
        expected="exported",
        actual=str(payload["status"]),
    )

    ctx.db.refresh(ctx.document)
    reporter.assert_true(
        ctx.document.workflow_status == DocumentWorkflowStatus.EXPORTED,
        stage="documentos",
        message="documentos exportados",
        expected=DocumentWorkflowStatus.EXPORTED.value,
        actual=ctx.document.workflow_status.value,
    )


def validate_traceability(ctx: SmokeContext, reporter: Reporter) -> None:
    assert ctx.batch_id is not None
    assert ctx.company is not None
    assert ctx.user is not None
    assert ctx.document is not None

    response = ctx.client.get(
        f"/api/v1/accounting/batches/{ctx.batch_id}",
        headers=ctx.auth_headers,
    )
    if response.status_code != 200:
        raise SmokeFailure(f"batch detail failed: {response.status_code} {response.text}")
    payload = response.json()

    expected_filename_pattern = rf"^SUENLACE_{str(ctx.company.id).replace('-', '')}_{str(ctx.batch_id).replace('-', '')}_\d{{8}}_\d{{6}}\.dat$"
    file_name = payload["file_name"]
    file_hash = payload["file_hash"]
    file_path = payload["file_path"]
    file_path_obj = Path(file_path)
    if file_path_obj not in ctx.created_paths:
        ctx.created_paths.append(file_path_obj)
    actual_hash = hashlib.sha256(file_path_obj.read_bytes()).hexdigest() if file_path_obj.exists() else ""

    reporter.assert_true(
        payload["a3_company_code_snapshot"] == _company_code_for(ctx.company.id),
        stage="trazabilidad",
        message="snapshot A3 conservado en lote",
        expected=_company_code_for(ctx.company.id),
        actual=str(payload["a3_company_code_snapshot"]),
    )
    reporter.assert_true(
        bool(payload["generated_at"]) and bool(payload["downloaded_at"]) and bool(payload["exported_at"]),
        stage="trazabilidad",
        message="fechas de generacion/descarga/exportacion informadas",
        expected="generated_at, downloaded_at y exported_at no nulos",
        actual=f"{payload['generated_at']} | {payload['downloaded_at']} | {payload['exported_at']}",
    )
    reporter.assert_true(
        payload["generated_by_user_id"] == str(ctx.user.id)
        and payload["downloaded_by_user_id"] == str(ctx.user.id)
        and payload["exported_by_user_id"] == str(ctx.user.id),
        stage="trazabilidad",
        message="usuarios de generacion/descarga/exportacion registrados",
        expected=str(ctx.user.id),
        actual=f"{payload['generated_by_user_id']} | {payload['downloaded_by_user_id']} | {payload['exported_by_user_id']}",
    )
    reporter.assert_true(
        bool(re.match(expected_filename_pattern, file_name or "")),
        stage="archivo",
        message="nombre de fichero cumple la convención prevista",
        expected=expected_filename_pattern,
        actual=str(file_name),
    )
    reporter.assert_true(
        file_path_obj.exists(),
        stage="archivo",
        message="fichero .dat existe físicamente",
        expected=str(file_path_obj),
        actual="exists" if file_path_obj.exists() else "missing",
    )
    reporter.assert_true(
        bool(file_hash) and file_hash == actual_hash,
        stage="archivo",
        message="hash SHA256 informado y correcto",
        expected=actual_hash,
        actual=str(file_hash),
    )
    reporter.assert_true(
        payload["total_documents"] == 1 and payload["total_entries"] == 2,
        stage="trazabilidad",
        message="total_documents y total_entries correctos",
        expected="1 documento / 2 entradas",
        actual=f"{payload['total_documents']} / {payload['total_entries']}",
    )

    actions = {
        event.action
        for event in ctx.db.query(DocumentEvent)
        .filter(DocumentEvent.document_id == ctx.document.id)
        .all()
    }
    expected_actions = {
        "accounting_batch_created",
        "accounting_batch_generated",
        "accounting_batch_downloaded",
        "accounting_batch_exported",
    }
    reporter.assert_true(
        expected_actions.issubset(actions),
        stage="trazabilidad",
        message="snapshot/hash/trazabilidad correctos",
        expected=", ".join(sorted(expected_actions)),
        actual=", ".join(sorted(actions)),
    )


def cleanup_run(ctx: SmokeContext) -> None:
    with suppress(Exception):
        for batch_id in ctx.created_batch_ids:
            ctx.db.query(AccountingBatchItem).filter(AccountingBatchItem.batch_id == batch_id).delete(synchronize_session=False)
            ctx.db.query(AccountingBatch).filter(AccountingBatch.id == batch_id).delete(synchronize_session=False)
        for document_id in ctx.created_document_ids:
            ctx.db.query(DocumentEvent).filter(DocumentEvent.document_id == document_id).delete(synchronize_session=False)
            ctx.db.query(InvoiceReview).filter(InvoiceReview.document_id == document_id).delete(synchronize_session=False)
            ctx.db.query(Document).filter(Document.id == document_id).delete(synchronize_session=False)
        ctx.db.commit()
    for path in reversed(ctx.created_paths):
        with suppress(Exception):
            if path.exists():
                path.unlink()


def _create_pending_accounting_document(
    ctx: SmokeContext,
    *,
    user: User,
    company: Company,
    supplier: GlobalThirdParty,
    supplier_account: CompanyAccount,
) -> Document:
    file_content = (
        "Smoke Phase 6 invoice\n"
        f"Run: {ctx.run_id}\n"
        "Base imponible: 100,00\n"
        "IVA 21%: 21,00\n"
        "Total factura: 121,00\n"
    ).encode("utf-8")
    sha256_hash = hashlib.sha256(file_content).hexdigest()
    company_folder = BACKEND_ROOT / "storage" / str(company.id) / "smoke_phase6"
    company_folder.mkdir(parents=True, exist_ok=True)
    stored_filename = f"smoke_phase6_{ctx.run_id}.txt"
    storage_path = company_folder / stored_filename
    storage_path.write_bytes(file_content)
    ctx.created_paths.append(storage_path)

    document = Document(
        company_id=company.id,
        original_filename=f"smoke_phase6_invoice_{ctx.run_id}.pdf",
        stored_filename=stored_filename,
        storage_path=str(storage_path),
        mime_type="application/pdf",
        extension=".pdf",
        file_size=len(file_content),
        sha256_hash=sha256_hash,
        source=DocumentSource.UPLOAD,
        document_type=DocumentType.INVOICE_RECEIVED,
        workflow_status=DocumentWorkflowStatus.PENDING_ACCOUNTING,
        uploaded_by_user_id=user.id,
        is_active=True,
    )
    ctx.db.add(document)
    ctx.db.flush()

    review = InvoiceReview(
        document_id=document.id,
        supplier_third_party_id=supplier.id,
        supplier_company_account_id=supplier_account.id,
        supplier_name_detected=SMOKE_SUPPLIER_NAME,
        supplier_tax_id_detected=SMOKE_SUPPLIER_TAX_ID,
        invoice_number=f"SMK-{ctx.run_id}",
        invoice_date=date.today(),
        taxable_base=100.00,
        tax_rate=21.00,
        tax_amount=21.00,
        total_amount=121.00,
        concept="Smoke test Phase 6 purchase",
        review_status=InvoiceReviewStatus.CONFIRMED,
        reviewed_by_user_id=user.id,
        reviewed_at=datetime.now(UTC),
    )
    ctx.db.add(review)
    ctx.db.flush()

    ctx.created_document_ids.append(document.id)
    document.invoice_review = review
    return document


def _company_code_for(company_id: uuid.UUID) -> str:
    digits = "".join(ch for ch in str(company_id) if ch.isdigit())
    return digits[:5].zfill(5) if digits else "00001"


if __name__ == "__main__":
    raise SystemExit(main())
