from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal


@dataclass(slots=True)
class FacturaeParty:
    nombre: str
    nif: str
    direccion: str
    cp: str
    poblacion: str
    provincia: str
    pais: str
    email: str = ""
    telefono: str = ""
    person_type: str = "J"
    residence_type: str = "R"


@dataclass(slots=True)
class FacturaeAdministrativeCentre:
    centre_code: str
    role_type_code: str
    name: str
    direccion: str
    cp: str
    poblacion: str
    provincia: str
    pais: str


@dataclass(slots=True)
class FacturaeTaxBreakdown:
    tax_type_code: str
    tax_rate: Decimal
    taxable_base: Decimal
    tax_amount: Decimal


@dataclass(slots=True)
class FacturaeLine:
    description: str
    quantity: Decimal
    unit_price: Decimal
    total_cost: Decimal
    gross_amount: Decimal
    tax_outputs: list[FacturaeTaxBreakdown] = field(default_factory=list)
    taxes_withheld: list[FacturaeTaxBreakdown] = field(default_factory=list)
    discount_amount: Decimal = Decimal("0.00")
    sequence_number: int = 1


@dataclass(slots=True)
class FacturaeCorrectiveData:
    invoice_number: str
    invoice_series_code: str = ""
    reason_code: str = "01"
    reason_description: str = "Factura rectificativa"


@dataclass(slots=True)
class FacturaeDocument:
    invoice_number: str
    invoice_series_code: str
    issue_date: str
    operation_date: str
    description: str
    file_reference: str
    receiver_contract_reference: str
    receiver_transaction_reference: str
    seller: FacturaeParty
    buyer: FacturaeParty
    administrative_centres: list[FacturaeAdministrativeCentre]
    invoice_lines: list[FacturaeLine]
    taxes_outputs: list[FacturaeTaxBreakdown]
    taxes_withheld: list[FacturaeTaxBreakdown]
    total_gross_amount: Decimal
    total_gross_amount_before_taxes: Decimal
    total_tax_outputs: Decimal
    total_taxes_withheld: Decimal
    invoice_total: Decimal
    total_outstanding_amount: Decimal
    total_executable_amount: Decimal
    invoice_class: str
    corrective: FacturaeCorrectiveData | None = None
