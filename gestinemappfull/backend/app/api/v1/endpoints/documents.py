from uuid import UUID

from fastapi import APIRouter, Depends, File, Query, UploadFile, status
from sqlalchemy.orm import Session

from app.api.deps import get_active_company_id, get_active_membership, get_current_user
from app.db.session import get_db
from app.models.company_membership import CompanyMembership
from app.models.enums import DocumentType, DocumentWorkflowStatus
from app.models.user import User
from app.schemas.document import DocumentRead, DocumentUpdate
from app.services.document_service import DocumentService


router = APIRouter(prefix="/documents")


@router.get("", response_model=list[DocumentRead])
def list_documents(
    document_type: DocumentType | None = Query(default=None),
    workflow_status: DocumentWorkflowStatus | None = Query(default=None),
    original_filename: str | None = Query(default=None),
    company_id=Depends(get_active_company_id),
    membership: CompanyMembership = Depends(get_active_membership),
    db: Session = Depends(get_db),
) -> list[DocumentRead]:
    del membership
    items = DocumentService(db).list(
        company_id=company_id,
        document_type=document_type,
        workflow_status=workflow_status,
        original_filename=original_filename,
    )
    return [DocumentRead.model_validate(item) for item in items]


@router.post("/upload", response_model=DocumentRead, status_code=status.HTTP_201_CREATED)
def upload_document(
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    company_id=Depends(get_active_company_id),
    membership: CompanyMembership = Depends(get_active_membership),
    db: Session = Depends(get_db),
) -> DocumentRead:
    del membership
    item = DocumentService(db).upload(company_id=company_id, uploaded_by=current_user, file=file)
    return DocumentRead.model_validate(item)


@router.patch("/{document_id}", response_model=DocumentRead)
def update_document(
    document_id: UUID,
    payload: DocumentUpdate,
    current_user: User = Depends(get_current_user),
    company_id=Depends(get_active_company_id),
    membership: CompanyMembership = Depends(get_active_membership),
    db: Session = Depends(get_db),
) -> DocumentRead:
    del membership
    item = DocumentService(db).update(
        company_id=company_id,
        document_id=document_id,
        current_user=current_user,
        payload=payload,
    )
    return DocumentRead.model_validate(item)
