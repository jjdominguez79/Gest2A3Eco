from __future__ import annotations

import hashlib
import uuid
from pathlib import Path

from fastapi import HTTPException, UploadFile, status
from sqlalchemy.orm import Session, joinedload

from app.core.config import settings
from app.models.document import Document
from app.models.enums import DocumentSource, DocumentType, DocumentWorkflowStatus
from app.models.user import User
from app.schemas.document import DocumentUpdate
from app.services.document_event_service import DocumentEventService


class DocumentService:
    def __init__(self, db: Session):
        self.db = db
        self._event_service = DocumentEventService(db)

    def list(
        self,
        *,
        company_id,
        document_type: DocumentType | None = None,
        workflow_status: DocumentWorkflowStatus | None = None,
        original_filename: str | None = None,
    ) -> list[Document]:
        query = self.db.query(Document).options(joinedload(Document.ocr_result)).filter(
            Document.company_id == company_id,
            Document.is_active.is_(True),
        )
        if document_type:
            query = query.filter(Document.document_type == document_type)
        if workflow_status:
            query = query.filter(Document.workflow_status == workflow_status)
        if original_filename:
            query = query.filter(Document.original_filename.ilike(f"%{original_filename.strip()}%"))
        return query.order_by(Document.created_at.desc()).all()

    def upload(self, *, company_id, uploaded_by: User, file: UploadFile) -> Document:
        original_filename = str(file.filename or "").strip()
        if not original_filename:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Filename is required.")

        extension = Path(original_filename).suffix.lower() or None
        stored_filename = f"{uuid.uuid4().hex}{extension or ''}"
        company_folder = Path(settings.document_storage_root) / str(company_id) / "documents"
        company_folder.mkdir(parents=True, exist_ok=True)
        final_path = company_folder / stored_filename

        sha256 = hashlib.sha256()
        file_size = 0

        with final_path.open("wb") as output_file:
            while True:
                chunk = file.file.read(1024 * 1024)
                if not chunk:
                    break
                sha256.update(chunk)
                file_size += len(chunk)
                output_file.write(chunk)
        file.file.close()

        document = Document(
            company_id=company_id,
            original_filename=original_filename,
            stored_filename=stored_filename,
            storage_path=str(final_path),
            mime_type=file.content_type,
            extension=extension,
            file_size=file_size,
            sha256_hash=sha256.hexdigest(),
            source=DocumentSource.UPLOAD,
            document_type=DocumentType.UNASSIGNED,
            workflow_status=DocumentWorkflowStatus.INBOX,
            uploaded_by_user_id=uploaded_by.id,
            is_active=True,
        )
        self.db.add(document)
        self.db.flush()
        self._event_service.create(
            document_id=document.id,
            user_id=uploaded_by.id,
            action="document_uploaded",
            details={
                "original_filename": original_filename,
                "storage_path": str(final_path),
                "file_size": file_size,
            },
        )
        self.db.commit()
        self.db.refresh(document)
        return document

    def update(self, *, company_id, document_id, current_user: User, payload: DocumentUpdate) -> Document:
        document = self.get_by_id(company_id=company_id, document_id=document_id)

        changes: dict[str, str] = {}
        if payload.document_type and payload.document_type != document.document_type:
            changes["document_type"] = f"{document.document_type.value}->{payload.document_type.value}"
            document.document_type = payload.document_type
        if payload.workflow_status and payload.workflow_status != document.workflow_status:
            changes["workflow_status"] = f"{document.workflow_status.value}->{payload.workflow_status.value}"
            document.workflow_status = payload.workflow_status

        if changes:
            self._event_service.create(
                document_id=document.id,
                user_id=current_user.id,
                action="document_updated",
                details=changes,
            )
            self.db.commit()
            self.db.refresh(document)
        return document

    def get_by_id(self, *, company_id, document_id) -> Document:
        document = (
            self.db.query(Document)
            .options(joinedload(Document.ocr_result))
            .filter(
                Document.id == document_id,
                Document.company_id == company_id,
                Document.is_active.is_(True),
            )
            .first()
        )
        if document is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found.")
        return document
