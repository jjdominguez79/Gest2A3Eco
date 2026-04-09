from __future__ import annotations

from sqlalchemy.orm import Session

from app.models.document_event import DocumentEvent


class DocumentEventService:
    def __init__(self, db: Session):
        self.db = db

    def create(self, *, document_id, user_id, action: str, details: dict | None = None) -> DocumentEvent:
        event = DocumentEvent(
            document_id=document_id,
            user_id=user_id,
            action=action,
            details=details or {},
        )
        self.db.add(event)
        return event
