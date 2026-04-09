from __future__ import annotations

import json
import re
from pathlib import Path

from fastapi import HTTPException, status
from sqlalchemy.orm import Session, joinedload

from app.models.document import Document
from app.models.document_ocr_result import DocumentOcrResult
from app.models.enums import DocumentOcrStatus, DocumentSource, DocumentType, DocumentWorkflowStatus
from app.models.user import User
from app.services.document_event_service import DocumentEventService


class OcrService:
    _TEXT_EXTENSIONS = {".txt", ".csv", ".json", ".xml", ".html", ".htm"}
    _IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp", ".gif", ".webp"}
    _OCR_KEYWORDS: dict[DocumentType, tuple[str, ...]] = {
        DocumentType.INVOICE_RECEIVED: ("factura recibida", "proveedor", "base imponible", "cuota", "iva soportado"),
        DocumentType.INVOICE_ISSUED: ("factura emitida", "cliente", "iva repercutido", "subtotal"),
        DocumentType.BANK_STATEMENT: ("extracto", "saldo", "movimientos", "iban", "cargo", "abono"),
        DocumentType.CONTRACT: ("contrato", "clausula", "acuerdo", "firmado", "arrendamiento"),
        DocumentType.BANK_RECEIPT: ("recibo", "adeudo", "domiciliacion", "remesa", "sepa"),
    }

    def __init__(self, db: Session):
        self.db = db
        self._event_service = DocumentEventService(db)

    def get_result(self, *, company_id, document_id) -> DocumentOcrResult:
        document = self._get_document(company_id=company_id, document_id=document_id)
        if document.ocr_result is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="OCR result not found.")
        return document.ocr_result

    def run(self, *, company_id, document_id, current_user: User) -> DocumentOcrResult:
        document = self._get_document(company_id=company_id, document_id=document_id)
        result = document.ocr_result or DocumentOcrResult(document_id=document.id)
        if document.ocr_result is None:
            self.db.add(result)
            self.db.flush()

        result.status = DocumentOcrStatus.PENDING
        result.error_message = None
        result.extracted_text = None
        result.extracted_data = {}
        result.confidence = None
        if document.workflow_status == DocumentWorkflowStatus.INBOX:
            document.workflow_status = DocumentWorkflowStatus.PENDING_OCR
        self._event_service.create(
            document_id=document.id,
            user_id=current_user.id,
            action="document_ocr_started",
            details={"document_type": document.document_type.value},
        )
        self.db.flush()

        try:
            extracted_text, extraction_meta = self._extract_text(document)
            inferred_type = self._infer_document_type(document=document, extracted_text=extracted_text)
            if document.document_type == DocumentType.UNASSIGNED and inferred_type != DocumentType.UNASSIGNED:
                document.document_type = inferred_type
            result.status = DocumentOcrStatus.PROCESSED
            result.extracted_text = extracted_text
            result.extracted_data = {
                "engine": extraction_meta["engine"],
                "document_type_suggestion": inferred_type.value,
                "extension": document.extension,
                "mime_type": document.mime_type,
            }
            result.confidence = extraction_meta["confidence"]
            result.error_message = None
            if document.workflow_status in {
                DocumentWorkflowStatus.INBOX,
                DocumentWorkflowStatus.PENDING_OCR,
                DocumentWorkflowStatus.CLASSIFIED,
            }:
                document.workflow_status = DocumentWorkflowStatus.PENDING_REVIEW
            self._event_service.create(
                document_id=document.id,
                user_id=current_user.id,
                action="document_ocr_processed",
                details={
                    "engine": extraction_meta["engine"],
                    "confidence": extraction_meta["confidence"],
                    "document_type": document.document_type.value,
                },
            )
            self.db.commit()
            self.db.refresh(result)
            return result
        except Exception as exc:
            result.status = DocumentOcrStatus.ERROR
            result.error_message = str(exc)
            result.extracted_text = None
            result.extracted_data = {}
            result.confidence = 0.0
            document.workflow_status = DocumentWorkflowStatus.ERROR
            self._event_service.create(
                document_id=document.id,
                user_id=current_user.id,
                action="document_ocr_failed",
                details={"error_message": str(exc)},
            )
            self.db.commit()
            self.db.refresh(result)
            return result

    def classify(self, *, company_id, document_id, current_user: User, document_type: DocumentType) -> Document:
        document = self._get_document(company_id=company_id, document_id=document_id)
        previous_type = document.document_type
        document.document_type = document_type
        if document_type == DocumentType.UNASSIGNED:
            if document.workflow_status == DocumentWorkflowStatus.CLASSIFIED:
                document.workflow_status = DocumentWorkflowStatus.INBOX
        elif document.workflow_status == DocumentWorkflowStatus.INBOX:
            document.workflow_status = DocumentWorkflowStatus.CLASSIFIED
        self._event_service.create(
            document_id=document.id,
            user_id=current_user.id,
            action="document_classified",
            details={
                "previous_document_type": previous_type.value,
                "document_type": document_type.value,
            },
        )
        self.db.commit()
        self.db.refresh(document)
        return document

    def _get_document(self, *, company_id, document_id) -> Document:
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

    def _extract_text(self, document: Document) -> tuple[str, dict[str, object]]:
        path = Path(document.storage_path)
        if not path.exists():
            raise ValueError("Document file does not exist in storage.")

        extension = (document.extension or path.suffix or "").lower()
        if extension in self._TEXT_EXTENSIONS:
            text = self._extract_plain_text(path)
            return text, {"engine": "plain_text", "confidence": 0.98}
        if extension == ".pdf":
            text = self._extract_pdf_text(path)
            return text, {"engine": "pypdf", "confidence": 0.8}
        if extension in self._IMAGE_EXTENSIONS:
            text = self._extract_image_text(path)
            return text, {"engine": "tesseract", "confidence": 0.65}
        raise ValueError(f"Document type {extension or 'unknown'} is not OCR compatible yet.")

    def _extract_plain_text(self, path: Path) -> str:
        for encoding in ("utf-8", "latin-1"):
            try:
                text = path.read_text(encoding=encoding)
                return self._normalize_text(text)
            except UnicodeDecodeError:
                continue
        raise ValueError("Could not decode text document.")

    def _extract_pdf_text(self, path: Path) -> str:
        try:
            from pypdf import PdfReader
        except ImportError as exc:
            raise RuntimeError("pypdf is required to process PDF OCR extraction.") from exc

        reader = PdfReader(str(path))
        pages = [page.extract_text() or "" for page in reader.pages]
        text = self._normalize_text("\n".join(pages))
        if not text:
            raise ValueError("No text could be extracted from PDF.")
        return text

    def _extract_image_text(self, path: Path) -> str:
        try:
            from PIL import Image
        except ImportError as exc:
            raise RuntimeError("Pillow is required to process image OCR.") from exc
        try:
            import pytesseract
        except ImportError as exc:
            raise RuntimeError("pytesseract is required to process image OCR.") from exc

        with Image.open(path) as image:
            text = pytesseract.image_to_string(image, lang="spa+eng")
        text = self._normalize_text(text)
        if not text:
            raise ValueError("No text could be extracted from image.")
        return text

    def _infer_document_type(self, *, document: Document, extracted_text: str) -> DocumentType:
        filename = (document.original_filename or "").lower()
        haystack = f"{filename}\n{extracted_text.lower()}"

        if document.source == DocumentSource.GENERATED_INTERNAL:
            return DocumentType.INVOICE_ISSUED
        if "emitida" in filename or "cliente" in haystack:
            return DocumentType.INVOICE_ISSUED
        if "recibida" in filename or "proveedor" in haystack:
            return DocumentType.INVOICE_RECEIVED
        if "extracto" in haystack or "movimientos" in haystack:
            return DocumentType.BANK_STATEMENT
        if "contrato" in haystack:
            return DocumentType.CONTRACT
        if "recibo" in haystack or "sepa" in haystack:
            return DocumentType.BANK_RECEIPT

        scores: dict[DocumentType, int] = {}
        for doc_type, keywords in self._OCR_KEYWORDS.items():
            scores[doc_type] = sum(1 for keyword in keywords if keyword in haystack)
        if scores:
            best_type = max(scores, key=scores.get)
            if scores[best_type] > 0:
                return best_type
        return DocumentType.UNASSIGNED

    def _normalize_text(self, text: str) -> str:
        normalized = text.replace("\x00", " ")
        normalized = re.sub(r"\r\n?", "\n", normalized)
        normalized = re.sub(r"[ \t]+", " ", normalized)
        normalized = re.sub(r"\n{3,}", "\n\n", normalized)
        normalized = normalized.strip()
        if normalized.startswith("{") or normalized.startswith("["):
            try:
                parsed = json.loads(normalized)
                normalized = json.dumps(parsed, ensure_ascii=False, indent=2)
            except json.JSONDecodeError:
                pass
        return normalized
