from enum import Enum


class ThirdPartyType(str, Enum):
    CLIENT = "client"
    SUPPLIER = "supplier"
    BOTH = "both"
    BANK = "bank"
    OTHER = "other"


class AccountType(str, Enum):
    CLIENT = "client"
    SUPPLIER = "supplier"
    BANK = "bank"
    EXPENSE = "expense"
    INCOME = "income"
    TAX = "tax"
    OTHER = "other"


class AccountSource(str, Enum):
    MANUAL_APP = "manual_app"
    A3_IMPORT = "a3_import"
    EXCEL_IMPORT = "excel_import"


class AccountSyncStatus(str, Enum):
    NOT_SYNCED = "not_synced"
    SYNCED = "synced"
    PENDING_SYNC = "pending_sync"
    SYNC_ERROR = "sync_error"


class DocumentSource(str, Enum):
    UPLOAD = "upload"
    EMAIL = "email"
    GENERATED_INTERNAL = "generated_internal"
    IMPORTED = "imported"


class DocumentType(str, Enum):
    INVOICE_ISSUED = "invoice_issued"
    INVOICE_RECEIVED = "invoice_received"
    BANK_STATEMENT = "bank_statement"
    CONTRACT = "contract"
    BANK_RECEIPT = "bank_receipt"
    UNASSIGNED = "unassigned"
    OTHER = "other"


class DocumentWorkflowStatus(str, Enum):
    INBOX = "inbox"
    CLASSIFIED = "classified"
    PENDING_REVIEW = "pending_review"
    PENDING_OCR = "pending_ocr"
    PENDING_ACCOUNTING = "pending_accounting"
    ACCOUNTED = "accounted"
    ARCHIVED = "archived"
    ERROR = "error"
