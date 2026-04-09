from datetime import date
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.api.deps import get_active_company_id, get_active_membership, get_current_user
from app.db.session import get_db
from app.models.company_membership import CompanyMembership
from app.models.enums import AccountingBatchStatus
from app.models.user import User
from app.schemas.accounting import (
    AccountingBatchCreate,
    AccountingBatchDownloadResponse,
    AccountingBatchExportMarkRequest,
    AccountingBatchGenerateRequest,
    AccountingBatchListItem,
    AccountingBatchRead,
    AccountingPendingItemRead,
)
from app.services.accounting_batch_service import AccountingBatchService


router = APIRouter(prefix="/accounting")


@router.get("/documents/pending", response_model=list[AccountingPendingItemRead])
@router.get("/pending", response_model=list[AccountingPendingItemRead], include_in_schema=False)
def list_accounting_pending_documents(
    company_id=Depends(get_active_company_id),
    membership: CompanyMembership = Depends(get_active_membership),
    db: Session = Depends(get_db),
) -> list[AccountingPendingItemRead]:
    del membership
    return AccountingBatchService(db).list_pending_documents(company_id=company_id)


@router.post("/batches", response_model=AccountingBatchRead)
def create_accounting_batch(
    payload: AccountingBatchCreate,
    current_user: User = Depends(get_current_user),
    company_id=Depends(get_active_company_id),
    membership: CompanyMembership = Depends(get_active_membership),
    db: Session = Depends(get_db),
) -> AccountingBatchRead:
    del membership
    return AccountingBatchService(db).create_batch_draft(
        company_id=company_id,
        current_user=current_user,
        payload=payload,
    )


@router.post("/batches/{batch_id}/generate", response_model=AccountingBatchRead)
def generate_accounting_batch(
    batch_id: UUID,
    payload: AccountingBatchGenerateRequest,
    current_user: User = Depends(get_current_user),
    company_id=Depends(get_active_company_id),
    membership: CompanyMembership = Depends(get_active_membership),
    db: Session = Depends(get_db),
) -> AccountingBatchRead:
    del membership
    return AccountingBatchService(db).generate_batch(
        company_id=company_id,
        batch_id=batch_id,
        current_user=current_user,
        payload=payload,
    )


@router.get("/batches", response_model=list[AccountingBatchListItem])
def list_accounting_batches(
    status_filter: AccountingBatchStatus | None = Query(default=None, alias="status"),
    date_from: date | None = Query(default=None),
    date_to: date | None = Query(default=None),
    company_id=Depends(get_active_company_id),
    membership: CompanyMembership = Depends(get_active_membership),
    db: Session = Depends(get_db),
) -> list[AccountingBatchListItem]:
    del membership
    return AccountingBatchService(db).list_batches(
        company_id=company_id,
        status_filter=status_filter,
        date_from=date_from,
        date_to=date_to,
    )


@router.get("/batches/{batch_id}", response_model=AccountingBatchRead)
def get_accounting_batch(
    batch_id: UUID,
    company_id=Depends(get_active_company_id),
    membership: CompanyMembership = Depends(get_active_membership),
    db: Session = Depends(get_db),
) -> AccountingBatchRead:
    del membership
    return AccountingBatchService(db).get_batch_detail(company_id=company_id, batch_id=batch_id)


@router.post("/batches/{batch_id}/download", response_model=None)
@router.get("/batches/{batch_id}/download", response_model=None, include_in_schema=False)
def download_accounting_batch(
    batch_id: UUID,
    current_user: User = Depends(get_current_user),
    company_id=Depends(get_active_company_id),
    membership: CompanyMembership = Depends(get_active_membership),
    db: Session = Depends(get_db),
):
    del membership
    path, filename, _ = AccountingBatchService(db).prepare_download(
        company_id=company_id,
        batch_id=batch_id,
        current_user=current_user,
    )
    return FileResponse(path, media_type="application/octet-stream", filename=filename)


@router.post("/batches/{batch_id}/download-metadata", response_model=AccountingBatchDownloadResponse, include_in_schema=False)
def download_accounting_batch_metadata(
    batch_id: UUID,
    current_user: User = Depends(get_current_user),
    company_id=Depends(get_active_company_id),
    membership: CompanyMembership = Depends(get_active_membership),
    db: Session = Depends(get_db),
) -> AccountingBatchDownloadResponse:
    del membership
    _, _, response = AccountingBatchService(db).prepare_download(
        company_id=company_id,
        batch_id=batch_id,
        current_user=current_user,
    )
    return response


@router.post("/batches/{batch_id}/mark-exported", response_model=AccountingBatchRead)
def mark_accounting_batch_exported(
    batch_id: UUID,
    payload: AccountingBatchExportMarkRequest,
    current_user: User = Depends(get_current_user),
    company_id=Depends(get_active_company_id),
    membership: CompanyMembership = Depends(get_active_membership),
    db: Session = Depends(get_db),
) -> AccountingBatchRead:
    del membership
    return AccountingBatchService(db).mark_exported(
        company_id=company_id,
        batch_id=batch_id,
        current_user=current_user,
        payload=payload,
    )
