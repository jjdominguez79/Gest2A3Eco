from __future__ import annotations

import re
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from difflib import SequenceMatcher

from fastapi import HTTPException, status
from sqlalchemy.orm import Session, joinedload

from app.models.company_account import CompanyAccount
from app.models.document import Document
from app.models.enums import AccountType, DocumentOcrStatus, DocumentType, DocumentWorkflowStatus, InvoiceReviewStatus
from app.models.global_third_party import GlobalThirdParty
from app.models.invoice_review import InvoiceReview
from app.models.user import User
from app.schemas.invoice_review import InvoiceReviewPendingItemRead, InvoiceReviewRead, InvoiceReviewUpdate
from app.schemas.invoice_review_suggestion import (
    InvoiceReviewSuggestionsRead,
    SuggestedCompanyAccountRead,
    SuggestedThirdPartyRead,
)
from app.services.document_event_service import DocumentEventService


class InvoiceReviewService:
    def __init__(self, db: Session):
        self.db = db
        self._event_service = DocumentEventService(db)

    def list_pending(self, *, company_id) -> list[InvoiceReviewPendingItemRead]:
        documents = (
            self.db.query(Document)
            .options(joinedload(Document.ocr_result), joinedload(Document.invoice_review))
            .filter(
                Document.company_id == company_id,
                Document.is_active.is_(True),
                Document.document_type == DocumentType.INVOICE_RECEIVED,
            )
            .order_by(Document.created_at.asc())
            .all()
        )
        items: list[InvoiceReviewPendingItemRead] = []
        for document in documents:
            review = document.invoice_review
            if review and review.review_status == InvoiceReviewStatus.CONFIRMED:
                continue
            if document.ocr_result is None:
                continue
            if document.ocr_result.status not in {DocumentOcrStatus.PROCESSED, DocumentOcrStatus.REVIEWED}:
                continue
            items.append(
                InvoiceReviewPendingItemRead(
                    document_id=document.id,
                    document_original_filename=document.original_filename,
                    document_created_at=document.created_at,
                    ocr_status=document.ocr_result.status.value,
                    ocr_confidence=document.ocr_result.confidence,
                    review_status=review.review_status if review else InvoiceReviewStatus.PENDING,
                    supplier_name_detected=review.supplier_name_detected if review else None,
                    supplier_tax_id_detected=review.supplier_tax_id_detected if review else None,
                    invoice_number=review.invoice_number if review else None,
                    total_amount=float(review.total_amount) if review and review.total_amount is not None else None,
                )
            )
        return items

    def get_by_document_id(self, *, company_id, document_id) -> InvoiceReviewRead:
        document = self._get_document(company_id=company_id, document_id=document_id)
        if document.invoice_review is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Invoice review not found.")
        return self._to_read(document.invoice_review)

    def initialize(self, *, company_id, document_id, current_user: User) -> InvoiceReviewRead:
        document = self._get_document(company_id=company_id, document_id=document_id, require_ocr=True)
        extracted = self._extract_invoice_data(document.ocr_result.extracted_text or "")
        review = document.invoice_review
        if review is None:
            review = InvoiceReview(document_id=document.id, review_status=InvoiceReviewStatus.PENDING)
            self.db.add(review)
            self.db.flush()

        review.supplier_name_detected = extracted["supplier_name_detected"]
        review.supplier_tax_id_detected = extracted["supplier_tax_id_detected"]
        review.invoice_number = extracted["invoice_number"]
        review.invoice_date = extracted["invoice_date"]
        review.taxable_base = extracted["taxable_base"]
        review.tax_rate = extracted["tax_rate"]
        review.tax_amount = extracted["tax_amount"]
        review.total_amount = extracted["total_amount"]
        review.concept = extracted["concept"]
        review.review_status = InvoiceReviewStatus.PENDING
        review.reviewed_by_user_id = current_user.id
        review.reviewed_at = datetime.now(UTC)
        if document.ocr_result.status == DocumentOcrStatus.PROCESSED:
            document.ocr_result.status = DocumentOcrStatus.REVIEWED
        if document.workflow_status in {DocumentWorkflowStatus.INBOX, DocumentWorkflowStatus.CLASSIFIED}:
            document.workflow_status = DocumentWorkflowStatus.PENDING_REVIEW
        self._event_service.create(
            document_id=document.id,
            user_id=current_user.id,
            action="invoice_review_initialized",
            details={
                "invoice_number": review.invoice_number,
                "supplier_tax_id_detected": review.supplier_tax_id_detected,
            },
        )
        self.db.commit()
        self.db.refresh(review)
        return self._to_read(review)

    def update(self, *, company_id, document_id, current_user: User, payload: InvoiceReviewUpdate) -> InvoiceReviewRead:
        document = self._get_document(company_id=company_id, document_id=document_id, require_ocr=True)
        review = document.invoice_review
        if review is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Invoice review not found.")

        provided_fields = payload.model_dump(exclude_unset=True)

        if "supplier_third_party_id" in provided_fields and payload.supplier_third_party_id:
            third_party = self.db.get(GlobalThirdParty, payload.supplier_third_party_id)
            if third_party is None or not third_party.is_active:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Global third party not found.")
        if "supplier_company_account_id" in provided_fields and payload.supplier_company_account_id:
            account = self._get_company_account(company_id=company_id, account_id=payload.supplier_company_account_id)
            if account.account_type.value not in {"supplier", "other"}:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Selected account is not valid for supplier linkage.")

        changes: dict[str, str] = {}
        for field_name in (
            "supplier_third_party_id",
            "supplier_company_account_id",
            "supplier_name_detected",
            "supplier_tax_id_detected",
            "invoice_number",
            "invoice_date",
            "taxable_base",
            "tax_rate",
            "tax_amount",
            "total_amount",
            "concept",
        ):
            if field_name not in provided_fields:
                continue
            value = provided_fields[field_name]
            if value != getattr(review, field_name):
                changes[field_name] = f"{getattr(review, field_name)}->{value}"
                setattr(review, field_name, value)

        if "review_status" in provided_fields and payload.review_status != InvoiceReviewStatus.CONFIRMED:
            if payload.review_status != review.review_status:
                changes["review_status"] = f"{review.review_status.value}->{payload.review_status.value}"
                review.review_status = payload.review_status

        if changes:
            if review.review_status == InvoiceReviewStatus.PENDING:
                review.review_status = InvoiceReviewStatus.REVIEWED
            review.reviewed_by_user_id = current_user.id
            review.reviewed_at = datetime.now(UTC)
            if document.ocr_result and document.ocr_result.status == DocumentOcrStatus.PROCESSED:
                document.ocr_result.status = DocumentOcrStatus.REVIEWED
            self._event_service.create(
                document_id=document.id,
                user_id=current_user.id,
                action="invoice_review_updated",
                details=changes,
            )
            self.db.commit()
            self.db.refresh(review)
        return self._to_read(review)

    def confirm(self, *, company_id, document_id, current_user: User) -> InvoiceReviewRead:
        document = self._get_document(company_id=company_id, document_id=document_id, require_ocr=True)
        review = document.invoice_review
        if review is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Invoice review not found.")
        if not review.invoice_number:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invoice number is required before confirmation.")
        if review.total_amount is None:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Total amount is required before confirmation.")

        review.review_status = InvoiceReviewStatus.CONFIRMED
        review.reviewed_by_user_id = current_user.id
        review.reviewed_at = datetime.now(UTC)
        document.workflow_status = DocumentWorkflowStatus.PENDING_ACCOUNTING
        if document.ocr_result and document.ocr_result.status in {DocumentOcrStatus.PROCESSED, DocumentOcrStatus.REVIEWED}:
            document.ocr_result.status = DocumentOcrStatus.REVIEWED
        self._event_service.create(
            document_id=document.id,
            user_id=current_user.id,
            action="invoice_review_confirmed",
            details={
                "invoice_number": review.invoice_number,
                "supplier_third_party_id": str(review.supplier_third_party_id) if review.supplier_third_party_id else None,
                "supplier_company_account_id": str(review.supplier_company_account_id) if review.supplier_company_account_id else None,
            },
        )
        self.db.commit()
        self.db.refresh(review)
        return self._to_read(review)

    def suggestions(self, *, company_id, document_id, current_user: User) -> InvoiceReviewSuggestionsRead:
        document = self._get_document(company_id=company_id, document_id=document_id, require_ocr=True)
        review = document.invoice_review
        if review is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Invoice review not found.")

        supplier_name = (review.supplier_name_detected or "").strip()
        supplier_tax_id = (review.supplier_tax_id_detected or "").strip().upper()

        third_party_candidates = (
            self.db.query(GlobalThirdParty)
            .filter(GlobalThirdParty.is_active.is_(True))
            .all()
        )
        account_candidates = (
            self.db.query(CompanyAccount)
            .filter(
                CompanyAccount.company_id == company_id,
                CompanyAccount.is_active.is_(True),
            )
            .all()
        )

        suggested_third_parties: list[SuggestedThirdPartyRead] = []
        for candidate in third_party_candidates:
            score, reason = self._score_third_party(
                candidate=candidate,
                supplier_tax_id=supplier_tax_id,
                supplier_name=supplier_name,
            )
            if score <= 0:
                continue
            suggested_third_parties.append(
                SuggestedThirdPartyRead(
                    id=candidate.id,
                    legal_name=candidate.legal_name,
                    tax_id=candidate.tax_id,
                    score=score,
                    reason=reason,
                )
            )
        suggested_third_parties.sort(key=lambda item: item.score, reverse=True)
        suggested_third_parties = suggested_third_parties[:5]

        suggested_accounts: list[SuggestedCompanyAccountRead] = []
        best_third_party_id = suggested_third_parties[0].id if suggested_third_parties else None
        for candidate in account_candidates:
            score, reason = self._score_company_account(
                candidate=candidate,
                supplier_tax_id=supplier_tax_id,
                supplier_name=supplier_name,
                best_third_party_id=best_third_party_id,
            )
            if score <= 0:
                continue
            suggested_accounts.append(
                SuggestedCompanyAccountRead(
                    id=candidate.id,
                    account_code=candidate.account_code,
                    name=candidate.name,
                    tax_id=candidate.tax_id,
                    global_third_party_id=candidate.global_third_party_id,
                    score=score,
                    reason=reason,
                )
            )
        suggested_accounts.sort(key=lambda item: item.score, reverse=True)
        suggested_accounts = suggested_accounts[:5]

        self._event_service.create(
            document_id=document.id,
            user_id=current_user.id,
            action="invoice_review_suggestions_requested",
            details={
                "best_third_party_id": str(best_third_party_id) if best_third_party_id else None,
                "third_party_candidates": len(suggested_third_parties),
                "account_candidates": len(suggested_accounts),
            },
        )
        self.db.commit()
        return InvoiceReviewSuggestionsRead(
            best_third_party_id=best_third_party_id,
            best_company_account_id=suggested_accounts[0].id if suggested_accounts else None,
            suggested_third_parties=suggested_third_parties,
            suggested_company_accounts=suggested_accounts,
        )

    def _get_document(self, *, company_id, document_id, require_ocr: bool = False) -> Document:
        document = (
            self.db.query(Document)
            .options(joinedload(Document.ocr_result), joinedload(Document.invoice_review))
            .filter(
                Document.id == document_id,
                Document.company_id == company_id,
                Document.is_active.is_(True),
                Document.document_type == DocumentType.INVOICE_RECEIVED,
            )
            .first()
        )
        if document is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Invoice received document not found.")
        if require_ocr:
            if document.ocr_result is None or document.ocr_result.status not in {DocumentOcrStatus.PROCESSED, DocumentOcrStatus.REVIEWED}:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="OCR processed result is required before invoice review.")
            if not (document.ocr_result.extracted_text or "").strip():
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="OCR text is empty for this document.")
        return document

    def _get_company_account(self, *, company_id, account_id) -> CompanyAccount:
        account = (
            self.db.query(CompanyAccount)
            .filter(
                CompanyAccount.id == account_id,
                CompanyAccount.company_id == company_id,
                CompanyAccount.is_active.is_(True),
            )
            .first()
        )
        if account is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Company account not found.")
        return account

    def _to_read(self, review: InvoiceReview) -> InvoiceReviewRead:
        document = review.document
        ocr_result = document.ocr_result if document else None
        return InvoiceReviewRead(
            id=review.id,
            document_id=review.document_id,
            supplier_third_party_id=review.supplier_third_party_id,
            supplier_company_account_id=review.supplier_company_account_id,
            supplier_name_detected=review.supplier_name_detected,
            supplier_tax_id_detected=review.supplier_tax_id_detected,
            invoice_number=review.invoice_number,
            invoice_date=review.invoice_date,
            taxable_base=float(review.taxable_base) if review.taxable_base is not None else None,
            tax_rate=float(review.tax_rate) if review.tax_rate is not None else None,
            tax_amount=float(review.tax_amount) if review.tax_amount is not None else None,
            total_amount=float(review.total_amount) if review.total_amount is not None else None,
            concept=review.concept,
            review_status=review.review_status,
            reviewed_by_user_id=review.reviewed_by_user_id,
            reviewed_at=review.reviewed_at,
            created_at=review.created_at,
            updated_at=review.updated_at,
            document_original_filename=document.original_filename if document else None,
            ocr_text=ocr_result.extracted_text if ocr_result else None,
            ocr_status=ocr_result.status.value if ocr_result else None,
        )

    def _extract_invoice_data(self, text: str) -> dict:
        lines = [line.strip() for line in text.splitlines() if line.strip()]

        supplier_name = None
        for line in lines[:8]:
            if re.search(r"(FACTURA|ALBARAN|FECHA|NIF|CIF|IVA|TOTAL)", line, re.IGNORECASE):
                continue
            if len(line) > 4:
                supplier_name = line
                break

        tax_id_match = re.search(r"\b([A-Z]\d{8}|\d{8}[A-Z]|[A-Z]\d{7}[A-Z0-9])\b", text.upper())
        number_match = re.search(r"(?:FACTURA|N[ÚU]MERO|NUMERO|N[ºO])[:\s#-]*([A-Z0-9\/\-]+)", text, re.IGNORECASE)
        date_match = re.search(r"\b(\d{1,2}[\/\-]\d{1,2}[\/\-]\d{2,4})\b", text)

        taxable_base = self._find_amount(text, ("base imponible", "base", "subtotal"))
        tax_amount = self._find_amount(text, ("iva", "cuota", "impuesto"))
        total_amount = self._find_amount(text, ("total factura", "importe total", "total"))
        tax_rate = self._find_percentage(text)
        concept = self._infer_concept(lines)

        if taxable_base is not None and tax_amount is not None and tax_rate is None and taxable_base != 0:
            try:
                tax_rate = ((tax_amount / taxable_base) * Decimal("100")).quantize(Decimal("0.01"))
            except InvalidOperation:
                tax_rate = None

        return {
            "supplier_name_detected": supplier_name,
            "supplier_tax_id_detected": tax_id_match.group(1) if tax_id_match else None,
            "invoice_number": number_match.group(1).strip() if number_match else None,
            "invoice_date": self._parse_date(date_match.group(1)) if date_match else None,
            "taxable_base": taxable_base,
            "tax_rate": tax_rate,
            "tax_amount": tax_amount,
            "total_amount": total_amount,
            "concept": concept,
        }

    def _find_amount(self, text: str, labels: tuple[str, ...]) -> Decimal | None:
        for label in labels:
            pattern = rf"{re.escape(label)}[^0-9\-]{{0,20}}(-?\d{{1,3}}(?:[.\s]\d{{3}})*,\d{{2}}|-?\d+(?:[.,]\d{{2}}))"
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                parsed = self._parse_decimal(match.group(1))
                if parsed is not None:
                    return parsed
        amounts = [self._parse_decimal(match) for match in re.findall(r"-?\d{1,3}(?:[.\s]\d{3})*,\d{2}|-?\d+(?:[.,]\d{2})", text)]
        amounts = [value for value in amounts if value is not None]
        return max(amounts) if amounts and "total" in text.lower() else None

    def _find_percentage(self, text: str) -> Decimal | None:
        match = re.search(r"(\d{1,2}(?:[.,]\d{1,2})?)\s*%", text)
        return self._parse_decimal(match.group(1)) if match else None

    def _infer_concept(self, lines: list[str]) -> str | None:
        concept_lines = []
        for line in lines:
            upper_line = line.upper()
            if any(token in upper_line for token in ("BASE", "IVA", "TOTAL", "FACTURA", "NIF", "CIF", "FECHA")):
                continue
            if re.fullmatch(r"[\d\s,.\-/%]+", line):
                continue
            if len(line) >= 8:
                concept_lines.append(line)
            if len(concept_lines) == 2:
                break
        return " | ".join(concept_lines) if concept_lines else None

    def _parse_decimal(self, raw: str | None) -> Decimal | None:
        if raw is None:
            return None
        normalized = raw.replace(" ", "").replace(".", "").replace(",", ".")
        try:
            return Decimal(normalized).quantize(Decimal("0.01"))
        except (InvalidOperation, ValueError):
            return None

    def _parse_date(self, raw: str | None):
        if raw is None:
            return None
        for fmt in ("%d/%m/%Y", "%d-%m-%Y", "%d/%m/%y", "%d-%m-%y"):
            try:
                return datetime.strptime(raw, fmt).date()
            except ValueError:
                continue
        return None

    def _score_third_party(self, *, candidate: GlobalThirdParty, supplier_tax_id: str, supplier_name: str) -> tuple[float, str]:
        if supplier_tax_id and candidate.tax_id and candidate.tax_id.upper() == supplier_tax_id:
            return 1.0, "tax_id_exact"
        if not supplier_name:
            return 0.0, ""
        similarity = SequenceMatcher(None, candidate.legal_name.lower(), supplier_name.lower()).ratio()
        if candidate.trade_name:
            similarity = max(similarity, SequenceMatcher(None, candidate.trade_name.lower(), supplier_name.lower()).ratio())
        if similarity >= 0.72:
            return round(similarity, 4), "name_similarity"
        return 0.0, ""

    def _score_company_account(
        self,
        *,
        candidate: CompanyAccount,
        supplier_tax_id: str,
        supplier_name: str,
        best_third_party_id,
    ) -> tuple[float, str]:
        score = 0.0
        reasons: list[str] = []
        if supplier_tax_id and candidate.tax_id and candidate.tax_id.upper() == supplier_tax_id:
            score += 0.8
            reasons.append("tax_id_exact")
        if best_third_party_id and candidate.global_third_party_id == best_third_party_id:
            score += 0.9
            reasons.append("linked_third_party")
        if supplier_name:
            similarity = SequenceMatcher(None, candidate.name.lower(), supplier_name.lower()).ratio()
            if candidate.legal_name:
                similarity = max(similarity, SequenceMatcher(None, candidate.legal_name.lower(), supplier_name.lower()).ratio())
            if similarity >= 0.70:
                score += similarity * 0.7
                reasons.append("name_similarity")
        if candidate.account_type == AccountType.SUPPLIER:
            score += 0.2
            reasons.append("supplier_account")
        return round(score, 4), ",".join(reasons)
