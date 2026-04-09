from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_active_company_id, get_active_membership, get_current_user
from app.db.session import get_db
from app.models.company_membership import CompanyMembership
from app.models.user import User
from app.schemas.invoice_review import InvoiceReviewPendingItemRead, InvoiceReviewRead, InvoiceReviewUpdate
from app.schemas.invoice_review_suggestion import InvoiceReviewSuggestionsRead
from app.services.invoice_review_service import InvoiceReviewService


router = APIRouter(prefix="/invoice-reviews")


@router.get("/pending", response_model=list[InvoiceReviewPendingItemRead])
def list_pending_invoice_reviews(
    company_id=Depends(get_active_company_id),
    membership: CompanyMembership = Depends(get_active_membership),
    db: Session = Depends(get_db),
) -> list[InvoiceReviewPendingItemRead]:
    del membership
    return InvoiceReviewService(db).list_pending(company_id=company_id)


@router.get("/{document_id}", response_model=InvoiceReviewRead)
def get_invoice_review(
    document_id: UUID,
    company_id=Depends(get_active_company_id),
    membership: CompanyMembership = Depends(get_active_membership),
    db: Session = Depends(get_db),
) -> InvoiceReviewRead:
    del membership
    return InvoiceReviewService(db).get_by_document_id(company_id=company_id, document_id=document_id)


@router.post("/{document_id}/initialize", response_model=InvoiceReviewRead)
def initialize_invoice_review(
    document_id: UUID,
    current_user: User = Depends(get_current_user),
    company_id=Depends(get_active_company_id),
    membership: CompanyMembership = Depends(get_active_membership),
    db: Session = Depends(get_db),
) -> InvoiceReviewRead:
    del membership
    return InvoiceReviewService(db).initialize(
        company_id=company_id,
        document_id=document_id,
        current_user=current_user,
    )


@router.patch("/{document_id}", response_model=InvoiceReviewRead)
def update_invoice_review(
    document_id: UUID,
    payload: InvoiceReviewUpdate,
    current_user: User = Depends(get_current_user),
    company_id=Depends(get_active_company_id),
    membership: CompanyMembership = Depends(get_active_membership),
    db: Session = Depends(get_db),
) -> InvoiceReviewRead:
    del membership
    return InvoiceReviewService(db).update(
        company_id=company_id,
        document_id=document_id,
        current_user=current_user,
        payload=payload,
    )


@router.post("/{document_id}/confirm", response_model=InvoiceReviewRead)
def confirm_invoice_review(
    document_id: UUID,
    current_user: User = Depends(get_current_user),
    company_id=Depends(get_active_company_id),
    membership: CompanyMembership = Depends(get_active_membership),
    db: Session = Depends(get_db),
) -> InvoiceReviewRead:
    del membership
    return InvoiceReviewService(db).confirm(
        company_id=company_id,
        document_id=document_id,
        current_user=current_user,
    )


@router.get("/{document_id}/suggestions", response_model=InvoiceReviewSuggestionsRead)
def get_invoice_review_suggestions(
    document_id: UUID,
    current_user: User = Depends(get_current_user),
    company_id=Depends(get_active_company_id),
    membership: CompanyMembership = Depends(get_active_membership),
    db: Session = Depends(get_db),
) -> InvoiceReviewSuggestionsRead:
    del membership
    return InvoiceReviewService(db).suggestions(
        company_id=company_id,
        document_id=document_id,
        current_user=current_user,
    )
