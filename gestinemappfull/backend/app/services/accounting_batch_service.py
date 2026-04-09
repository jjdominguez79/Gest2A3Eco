from __future__ import annotations

import hashlib
import uuid
from datetime import date, datetime
from pathlib import Path

from fastapi import HTTPException, status
from sqlalchemy import func
from sqlalchemy.orm import Session, joinedload

from app.core.config import settings
from app.models.accounting_batch import AccountingBatch
from app.models.accounting_batch_item import AccountingBatchItem
from app.models.company import Company
from app.models.document import Document
from app.models.enums import (
    AccountingBatchItemStatus,
    AccountingBatchStatus,
    AccountingBatchType,
    DocumentType,
    DocumentWorkflowStatus,
    InvoiceReviewStatus,
)
from app.models.invoice_review import InvoiceReview
from app.models.user import User
from app.schemas.accounting import (
    AccountingBatchCreate,
    AccountingBatchDownloadResponse,
    AccountingBatchExportMarkRequest,
    AccountingBatchGenerateRequest,
    AccountingBatchItemRead,
    AccountingBatchListItem,
    AccountingBatchRead,
    AccountingPendingItemRead,
)
from app.services.document_event_service import DocumentEventService


class AccountingBatchService:
    def __init__(self, db: Session):
        self.db = db
        self._event_service = DocumentEventService(db)

    def list_pending_documents(self, *, company_id) -> list[AccountingPendingItemRead]:
        reviews = (
            self.db.query(InvoiceReview)
            .options(
                joinedload(InvoiceReview.document),
                joinedload(InvoiceReview.supplier_company_account),
            )
            .join(Document, InvoiceReview.document_id == Document.id)
            .filter(
                Document.company_id == company_id,
                Document.is_active.is_(True),
                Document.document_type == DocumentType.INVOICE_RECEIVED,
                Document.workflow_status == DocumentWorkflowStatus.PENDING_ACCOUNTING,
                InvoiceReview.review_status == InvoiceReviewStatus.CONFIRMED,
            )
            .order_by(InvoiceReview.invoice_date.asc().nullslast(), Document.created_at.asc())
            .all()
        )
        if not reviews:
            return []

        latest_batch_rows = (
            self.db.query(
                AccountingBatchItem.document_id,
                AccountingBatch.id,
                AccountingBatch.status,
            )
            .join(AccountingBatch, AccountingBatch.id == AccountingBatchItem.batch_id)
            .filter(
                AccountingBatch.company_id == company_id,
                AccountingBatchItem.document_id.in_([item.document_id for item in reviews]),
            )
            .order_by(AccountingBatch.created_at.desc())
            .all()
        )
        latest_batch_by_document: dict[uuid.UUID, tuple[uuid.UUID, AccountingBatchStatus]] = {}
        for document_id, batch_id, batch_status in latest_batch_rows:
            latest_batch_by_document.setdefault(document_id, (batch_id, batch_status))

        return [
            AccountingPendingItemRead(
                document_id=item.document_id,
                invoice_review_id=item.id,
                original_filename=item.document.original_filename,
                supplier_name=item.supplier_name_detected,
                supplier_tax_id=item.supplier_tax_id_detected,
                invoice_number=item.invoice_number,
                invoice_date=datetime.combine(item.invoice_date, datetime.min.time()) if item.invoice_date else None,
                total_amount=float(item.total_amount) if item.total_amount is not None else None,
                company_account_code=item.supplier_company_account.account_code if item.supplier_company_account else None,
                workflow_status=item.document.workflow_status,
                latest_batch_id=latest_batch_by_document.get(item.document_id, (None, None))[0],
                latest_batch_status=latest_batch_by_document.get(item.document_id, (None, None))[1],
            )
            for item in reviews
        ]

    def create_batch_draft(
        self,
        *,
        company_id,
        current_user: User,
        payload: AccountingBatchCreate,
    ) -> AccountingBatchRead:
        document_ids = list(dict.fromkeys(payload.document_ids))
        if not document_ids:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="At least one document must be selected.")

        documents = self._get_documents_for_batch(company_id=company_id, document_ids=document_ids)
        for document in documents:
            self._validate_document_for_batch(document)
            self._ensure_document_not_already_batched(document_id=document.id, company_id=company_id)

        batch = AccountingBatch(
            company_id=company_id,
            batch_type=AccountingBatchType.INVOICE_RECEIVED,
            status=AccountingBatchStatus.DRAFT,
            created_by_user_id=current_user.id,
            total_documents=len(documents),
            total_entries=0,
            notes=(payload.notes or "").strip() or None,
        )
        self.db.add(batch)
        self.db.flush()

        for document in documents:
            self.db.add(
                AccountingBatchItem(
                    batch_id=batch.id,
                    document_id=document.id,
                    invoice_review_id=document.invoice_review.id if document.invoice_review else None,
                    status=AccountingBatchItemStatus.INCLUDED,
                    error_message=None,
                )
            )
            self._event_service.create(
                document_id=document.id,
                user_id=current_user.id,
                action="accounting_batch_created",
                details={"batch_id": str(batch.id)},
            )

        self.db.commit()
        return self.get_batch_detail(company_id=company_id, batch_id=batch.id)

    def generate_batch(
        self,
        *,
        company_id,
        batch_id,
        current_user: User,
        payload: AccountingBatchGenerateRequest | None = None,
    ) -> AccountingBatchRead:
        batch = self._get_batch(company_id=company_id, batch_id=batch_id, with_items=True)
        if batch.status != AccountingBatchStatus.DRAFT:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Only draft batches can be generated.")
        if not batch.items:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="The batch does not contain documents.")

        documents = [item.document for item in batch.items if item.document is not None]
        for document in documents:
            self._validate_document_for_batch(document)

        company = self.db.get(Company, company_id)
        if company is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Company not found.")

        try:
            generated_at = datetime.utcnow()
            a3_company_code_snapshot = self._resolve_company_code(company)
            content, total_entries = self._render_suenlace(documents=documents, company_code=a3_company_code_snapshot)
            content_bytes = content.encode("latin-1", errors="replace")
            file_hash = hashlib.sha256(content_bytes).hexdigest()

            folder = Path(settings.document_storage_root) / str(company_id) / "accounting_batches"
            folder.mkdir(parents=True, exist_ok=True)
            file_name = self._build_file_name(
                company_id=company_id,
                batch_id=batch.id,
                generated_at=generated_at,
            )
            final_path = folder / file_name
            final_path.write_bytes(content_bytes)

            batch.status = AccountingBatchStatus.GENERATED
            batch.a3_company_code_snapshot = a3_company_code_snapshot
            batch.file_name = file_name
            batch.file_path = str(final_path)
            batch.file_hash = file_hash
            batch.generated_at = generated_at
            batch.generated_by_user_id = current_user.id
            batch.total_documents = len(documents)
            batch.total_entries = total_entries
            if payload and payload.notes is not None:
                batch.notes = (payload.notes or "").strip() or None
            batch.error_message = None

            for document in documents:
                document.workflow_status = DocumentWorkflowStatus.BATCHED
                self._event_service.create(
                    document_id=document.id,
                    user_id=current_user.id,
                    action="accounting_batch_generated",
                    details={
                        "batch_id": str(batch.id),
                        "file_name": file_name,
                        "file_hash": file_hash,
                        "workflow_status": DocumentWorkflowStatus.BATCHED.value,
                    },
                )

            self.db.commit()
            return self.get_batch_detail(company_id=company_id, batch_id=batch.id)
        except Exception as exc:
            self.db.rollback()
            batch = self._get_batch(company_id=company_id, batch_id=batch_id, with_items=False)
            batch.status = AccountingBatchStatus.ERROR
            batch.error_message = str(exc)
            self.db.commit()
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Could not generate suenlace.dat: {exc}",
            )

    def list_batches(
        self,
        *,
        company_id,
        status_filter: AccountingBatchStatus | None = None,
        date_from: date | None = None,
        date_to: date | None = None,
    ) -> list[AccountingBatchListItem]:
        query = (
            self.db.query(AccountingBatch)
            .options(
                joinedload(AccountingBatch.created_by),
                joinedload(AccountingBatch.generated_by),
                joinedload(AccountingBatch.downloaded_by),
                joinedload(AccountingBatch.exported_by),
            )
            .filter(AccountingBatch.company_id == company_id)
        )
        if status_filter is not None:
            query = query.filter(AccountingBatch.status == status_filter)
        if date_from is not None:
            query = query.filter(func.date(AccountingBatch.created_at) >= date_from)
        if date_to is not None:
            query = query.filter(func.date(AccountingBatch.created_at) <= date_to)
        batches = query.order_by(AccountingBatch.created_at.desc()).all()
        return [self._to_batch_list_item(item) for item in batches]

    def get_batch_detail(self, *, company_id, batch_id) -> AccountingBatchRead:
        batch = self._get_batch(company_id=company_id, batch_id=batch_id, with_items=True)
        return self._to_batch_read(batch)

    def prepare_download(
        self,
        *,
        company_id,
        batch_id,
        current_user: User,
    ) -> tuple[str, str, AccountingBatchDownloadResponse]:
        batch = self._get_batch(company_id=company_id, batch_id=batch_id, with_items=True)
        if not batch.file_path or not batch.file_name:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Accounting batch file not found.")
        path = Path(batch.file_path)
        if not path.exists():
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Accounting batch file not found on disk.")

        if batch.status == AccountingBatchStatus.GENERATED:
            batch.status = AccountingBatchStatus.DOWNLOADED
            batch.downloaded_at = datetime.utcnow()
            batch.downloaded_by_user_id = current_user.id
            for item in batch.items:
                self._event_service.create(
                    document_id=item.document_id,
                    user_id=current_user.id,
                    action="accounting_batch_downloaded",
                    details={"batch_id": str(batch.id), "file_name": batch.file_name},
                )
            self.db.commit()

        response = AccountingBatchDownloadResponse(
            batch_id=batch.id,
            status=batch.status,
            downloaded_at=batch.downloaded_at,
            downloaded_by_user_id=batch.downloaded_by_user_id,
        )
        return str(path), batch.file_name, response

    def mark_exported(
        self,
        *,
        company_id,
        batch_id,
        current_user: User,
        payload: AccountingBatchExportMarkRequest | None = None,
    ) -> AccountingBatchRead:
        batch = self._get_batch(company_id=company_id, batch_id=batch_id, with_items=True)
        if batch.status not in {AccountingBatchStatus.GENERATED, AccountingBatchStatus.DOWNLOADED}:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Only generated or downloaded batches can be marked as exported.",
            )

        batch.status = AccountingBatchStatus.EXPORTED
        batch.exported_at = datetime.utcnow()
        batch.exported_by_user_id = current_user.id
        if payload and payload.notes:
            note = payload.notes.strip()
            batch.notes = note or batch.notes

        for item in batch.items:
            if item.document is None:
                continue
            item.document.workflow_status = DocumentWorkflowStatus.EXPORTED
            self._event_service.create(
                document_id=item.document_id,
                user_id=current_user.id,
                action="accounting_batch_exported",
                details={
                    "batch_id": str(batch.id),
                    "workflow_status": DocumentWorkflowStatus.EXPORTED.value,
                },
            )

        self.db.commit()
        return self.get_batch_detail(company_id=company_id, batch_id=batch.id)

    def _get_documents_for_batch(self, *, company_id, document_ids: list[uuid.UUID]) -> list[Document]:
        documents = (
            self.db.query(Document)
            .options(
                joinedload(Document.invoice_review).joinedload(InvoiceReview.supplier_company_account),
                joinedload(Document.accounting_batch_items).joinedload(AccountingBatchItem.batch),
            )
            .filter(
                Document.company_id == company_id,
                Document.id.in_(document_ids),
                Document.is_active.is_(True),
            )
            .all()
        )
        found_ids = {item.id for item in documents}
        missing = [str(doc_id) for doc_id in document_ids if doc_id not in found_ids]
        if missing:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Documents not found: {', '.join(missing)}")
        documents.sort(key=lambda item: document_ids.index(item.id))
        return documents

    def _get_batch(self, *, company_id, batch_id, with_items: bool) -> AccountingBatch:
        query = self.db.query(AccountingBatch).filter(
            AccountingBatch.id == batch_id,
            AccountingBatch.company_id == company_id,
        )
        if with_items:
            query = query.options(
                joinedload(AccountingBatch.created_by),
                joinedload(AccountingBatch.generated_by),
                joinedload(AccountingBatch.downloaded_by),
                joinedload(AccountingBatch.exported_by),
                joinedload(AccountingBatch.items).joinedload(AccountingBatchItem.document),
                joinedload(AccountingBatch.items).joinedload(AccountingBatchItem.invoice_review),
            )
        batch = query.first()
        if batch is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Accounting batch not found.")
        return batch

    def _ensure_document_not_already_batched(self, *, document_id, company_id) -> None:
        existing = (
            self.db.query(AccountingBatchItem)
            .join(AccountingBatch, AccountingBatch.id == AccountingBatchItem.batch_id)
            .filter(
                AccountingBatch.company_id == company_id,
                AccountingBatchItem.document_id == document_id,
                AccountingBatch.status.in_(
                    [
                        AccountingBatchStatus.DRAFT,
                        AccountingBatchStatus.GENERATED,
                        AccountingBatchStatus.DOWNLOADED,
                        AccountingBatchStatus.EXPORTED,
                    ]
                ),
            )
            .first()
        )
        if existing is not None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Document {document_id} is already included in another batch.",
            )

    def _validate_document_for_batch(self, document: Document) -> None:
        if document.document_type != DocumentType.INVOICE_RECEIVED:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Document {document.id} is not invoice_received.")
        if document.workflow_status != DocumentWorkflowStatus.PENDING_ACCOUNTING:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Document {document.id} is not pending_accounting.")
        review = document.invoice_review
        if review is None or review.review_status != InvoiceReviewStatus.CONFIRMED:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Document {document.id} does not have confirmed invoice review.")
        if review.supplier_company_account is None:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Document {document.id} requires supplier company account before batching.")

    def _render_suenlace(self, *, documents: list[Document], company_code: str) -> tuple[str, int]:
        rows: list[str] = []
        for document in sorted(documents, key=lambda item: (item.invoice_review.invoice_date or date.today(), item.created_at)):
            review = document.invoice_review
            supplier_account = review.supplier_company_account.account_code
            rows.append(
                self._render_purchase_header(
                    company_code=company_code,
                    invoice_date=review.invoice_date or document.created_at.date(),
                    supplier_account=supplier_account,
                    invoice_number=review.invoice_number or str(document.id)[:10],
                    description=f"Su Fra Nº. {review.invoice_number or document.original_filename}",
                    total_amount=float(review.total_amount or 0),
                    supplier_tax_id=review.supplier_tax_id_detected or "",
                    supplier_name=review.supplier_name_detected or "",
                )
            )
            pct = float(review.tax_rate or 0)
            rows.append(
                self._render_purchase_detail(
                    company_code=company_code,
                    invoice_date=review.invoice_date or document.created_at.date(),
                    expense_account="629000000000",
                    invoice_number=review.invoice_number or str(document.id)[:10],
                    description=review.concept or "Compras",
                    base=float(review.taxable_base or 0),
                    pct_iva=pct,
                    cuota_iva=float(review.tax_amount or 0),
                    is_last=True,
                )
            )
        return "".join(rows), len(rows)

    def _resolve_company_code(self, company: Company) -> str:
        if company.a3_company_code:
            return company.a3_company_code
        digits = "".join(ch for ch in str(company.id) if ch.isdigit())
        return digits[:5].zfill(5) if digits else "00001"

    def _build_file_name(self, *, company_id, batch_id, generated_at: datetime) -> str:
        timestamp = generated_at.strftime("%Y%m%d_%H%M%S")
        return f"SUENLACE_{str(company_id).replace('-', '')}_{str(batch_id).replace('-', '')}_{timestamp}.dat"

    def _render_purchase_header(
        self,
        *,
        company_code: str,
        invoice_date: date,
        supplier_account: str,
        invoice_number: str,
        description: str,
        total_amount: float,
        supplier_tax_id: str,
        supplier_name: str,
    ) -> str:
        buf = [" "] * 254
        self._set(buf, 0, 1, "4")
        self._set(buf, 1, 6, company_code)
        self._set(buf, 6, 14, self._yyyymmdd(invoice_date))
        self._set(buf, 14, 15, "1")
        self._set(buf, 15, 27, self._account12(supplier_account))
        self._set(buf, 57, 58, "2")
        self._set(buf, 58, 68, invoice_number[:10])
        self._set(buf, 68, 69, "I")
        self._set(buf, 69, 99, description[:30])
        self._set(buf, 99, 113, self._amount14(total_amount))
        self._set(buf, 175, 189, supplier_tax_id[:14])
        self._set(buf, 189, 229, supplier_name[:40])
        self._set(buf, 236, 244, self._yyyymmdd(invoice_date))
        self._set(buf, 244, 252, self._yyyymmdd(invoice_date))
        self._set(buf, 252, 253, "E")
        self._set(buf, 253, 254, "N")
        return "".join(buf) + "\r\n"

    def _render_purchase_detail(
        self,
        *,
        company_code: str,
        invoice_date: date,
        expense_account: str,
        invoice_number: str,
        description: str,
        base: float,
        pct_iva: float,
        cuota_iva: float,
        is_last: bool,
    ) -> str:
        buf = [" "] * 254
        self._set(buf, 0, 1, "4")
        self._set(buf, 1, 6, company_code)
        self._set(buf, 6, 14, self._yyyymmdd(invoice_date))
        self._set(buf, 14, 15, "9")
        self._set(buf, 15, 27, self._account12(expense_account))
        self._set(buf, 57, 58, "C")
        self._set(buf, 58, 68, invoice_number[:10])
        self._set(buf, 68, 69, "U" if is_last else "M")
        self._set(buf, 69, 99, description[:30])
        self._set(buf, 99, 101, "01")
        self._set(buf, 101, 115, self._amount14(base))
        self._set(buf, 115, 120, f"{abs(pct_iva):05.2f}"[-5:])
        self._set(buf, 120, 134, self._amount14(cuota_iva))
        self._set(buf, 172, 175, "01S" if abs(pct_iva) > 0 else "01N")
        self._set(buf, 252, 253, "E")
        self._set(buf, 253, 254, "N")
        return "".join(buf) + "\r\n"

    def _yyyymmdd(self, value: date | datetime) -> str:
        if isinstance(value, datetime):
            value = value.date()
        return value.strftime("%Y%m%d")

    def _account12(self, value: str) -> str:
        digits = "".join(ch for ch in str(value) if ch.isdigit())
        return digits[:12].ljust(12, "0")

    def _amount14(self, value: float) -> str:
        rendered = f"{abs(float(value or 0)):.2f}"
        integer, decimal = rendered.split(".")
        return f"+{integer.zfill(10)[-10:]}.{decimal}"

    def _set(self, buf: list[str], start: int, end: int, value: str) -> None:
        text = str(value)[: end - start].ljust(end - start)
        buf[start:end] = list(text)

    def _to_batch_list_item(self, batch: AccountingBatch) -> AccountingBatchListItem:
        return AccountingBatchListItem(
            id=batch.id,
            company_id=batch.company_id,
            batch_type=batch.batch_type,
            status=batch.status,
            a3_company_code_snapshot=batch.a3_company_code_snapshot,
            file_name=batch.file_name,
            file_path=batch.file_path,
            file_hash=batch.file_hash,
            created_by_user_id=batch.created_by_user_id,
            generated_by_user_id=batch.generated_by_user_id,
            downloaded_by_user_id=batch.downloaded_by_user_id,
            exported_by_user_id=batch.exported_by_user_id,
            created_by_name=batch.created_by.full_name if batch.created_by else None,
            generated_by_name=batch.generated_by.full_name if batch.generated_by else None,
            downloaded_by_name=batch.downloaded_by.full_name if batch.downloaded_by else None,
            exported_by_name=batch.exported_by.full_name if batch.exported_by else None,
            created_at=batch.created_at,
            generated_at=batch.generated_at,
            downloaded_at=batch.downloaded_at,
            exported_at=batch.exported_at,
            total_documents=batch.total_documents,
            total_entries=batch.total_entries,
            notes=batch.notes,
            error_message=batch.error_message,
        )

    def _to_batch_read(self, batch: AccountingBatch) -> AccountingBatchRead:
        base = self._to_batch_list_item(batch)
        items = [
            AccountingBatchItemRead(
                id=item.id,
                batch_id=item.batch_id,
                document_id=item.document_id,
                invoice_review_id=item.invoice_review_id,
                status=item.status,
                error_message=item.error_message,
                created_at=item.created_at,
                original_filename=item.document.original_filename if item.document else None,
                invoice_number=item.invoice_review.invoice_number if item.invoice_review else None,
                workflow_status=item.document.workflow_status if item.document else None,
            )
            for item in batch.items
        ]
        return AccountingBatchRead(**base.model_dump(), items=items)
