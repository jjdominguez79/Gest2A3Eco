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
