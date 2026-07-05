from __future__ import annotations

from collections import defaultdict
from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP
from xml.etree import ElementTree as ET

from services.facturae.facturae_codes import (
    ADMIN_CENTRE_ROLE_MANAGER,
    ADMIN_CENTRE_ROLE_OFFICE,
    ADMIN_CENTRE_ROLE_PROCESSING,
    ADMIN_CENTRE_ROLE_PROPONENT,
    DS_NS,
    FACTURAE_NS,
    INVOICE_DOCUMENT_TYPE,
    INVOICE_ISSUER_TYPE,
    MODALITY_INDIVIDUAL,
    SCHEMA_LOCATION,
    SCHEMA_VERSION,
    TAX_TYPE_IRPF,
    TAX_TYPE_VAT,
    UNIT_OF_MEASURE_UNITS,
    XSI_NS,
)
from services.facturae.facturae_models import (
    FacturaeAdministrativeCentre,
    FacturaeCorrectiveData,
    FacturaeDocument,
    FacturaeLine,
    FacturaeParty,
    FacturaeTaxBreakdown,
)
from services.facturae.facturae_validator import d2


Q6 = Decimal("0.000001")


def _tag(name: str) -> str:
    return f"{{{FACTURAE_NS}}}{name}"


def _sub(parent: ET.Element, tag: str) -> ET.Element:
    return ET.SubElement(parent, _tag(tag))


def q6(value: Decimal) -> Decimal:
    return Decimal(str(value or 0)).quantize(Q6, rounding=ROUND_HALF_UP)


def _txt(parent: ET.Element, tag: str, value) -> ET.Element:
    node = _sub(parent, tag)
    node.text = str(value)
    return node


def _amount(parent: ET.Element, tag: str, amount: Decimal) -> ET.Element:
    node = _sub(parent, tag)
    _txt(node, "TotalAmount", f"{d2(amount):.2f}")
    return node


def _format_date(value: str) -> str:
    raw = str(value or "").strip()
    for fmt in ("%d/%m/%Y", "%Y-%m-%d", "%Y-%m-%d %H:%M:%S"):
        try:
            return datetime.strptime(raw, fmt).strftime("%Y-%m-%d")
        except Exception:
            continue
    return raw


def _country_to_alpha3(value: str) -> str:
    code = str(value or "").strip().upper()
    mapping = {
        "ES": "ESP",
        "PT": "PRT",
        "FR": "FRA",
        "DE": "DEU",
        "IT": "ITA",
        "GB": "GBR",
        "UK": "GBR",
        "NL": "NLD",
        "BE": "BEL",
        "IE": "IRL",
    }
    if len(code) == 3:
        return code
    return mapping.get(code, "ESP" if not code else code)


def _build_party(raw: dict) -> FacturaeParty:
    nif = str(raw.get("nif") or "").strip().upper()
    pais = str(raw.get("pais") or "").strip().upper() or "ES"
    person_type = "J"
    if nif and nif[:1].isdigit():
        person_type = "F"
    residence_type = "R"
    if len(pais) == 2 and pais != "ES":
        residence_type = "U" if pais in {"AT", "BE", "BG", "CY", "CZ", "DE", "DK", "EE", "EL", "FI", "FR", "HR", "HU", "IE", "IT", "LT", "LU", "LV", "MT", "NL", "PL", "PT", "RO", "SE", "SI", "SK"} else "E"
    return FacturaeParty(
        nombre=str(raw.get("nombre_legal") or raw.get("nombre") or "").strip(),
        nif=nif,
        direccion=str(raw.get("direccion") or "").strip(),
        cp=str(raw.get("cp") or "").strip(),
        poblacion=str(raw.get("poblacion") or "").strip(),
        provincia=str(raw.get("provincia") or "").strip(),
        pais=_country_to_alpha3(pais),
        email=str(raw.get("email") or "").strip(),
        telefono=str(raw.get("telefono") or "").strip(),
        person_type=person_type,
        residence_type=residence_type,
    )


def _build_admin_centres(rel: dict, buyer: FacturaeParty) -> list[FacturaeAdministrativeCentre]:
    if not rel.get("facturae_es_administracion_publica"):
        return []
    base = {
        "direccion": buyer.direccion,
        "cp": buyer.cp,
        "poblacion": buyer.poblacion,
        "provincia": buyer.provincia,
        "pais": buyer.pais,
    }
    rows: list[FacturaeAdministrativeCentre] = []
    for code, role, name in (
        (rel.get("facturae_dir3_oficina_contable"), ADMIN_CENTRE_ROLE_OFFICE, "Oficina contable"),
        (rel.get("facturae_dir3_organo_gestor"), ADMIN_CENTRE_ROLE_MANAGER, "Organo gestor"),
        (rel.get("facturae_dir3_unidad_tramitadora"), ADMIN_CENTRE_ROLE_PROCESSING, "Unidad tramitadora"),
        (rel.get("facturae_dir3_organo_proponente"), ADMIN_CENTRE_ROLE_PROPONENT, "Organo proponente"),
    ):
        if not str(code or "").strip():
            continue
        rows.append(
            FacturaeAdministrativeCentre(
                centre_code=str(code).strip().upper(),
                role_type_code=role,
                name=name,
                **base,
            )
        )
    return rows


def _tax(rate: Decimal, base: Decimal, amount: Decimal, tax_type_code: str) -> FacturaeTaxBreakdown:
    return FacturaeTaxBreakdown(
        tax_type_code=tax_type_code,
        tax_rate=d2(rate),
        taxable_base=d2(base),
        tax_amount=d2(amount),
    )


def build_facturae_document(payload: dict) -> FacturaeDocument:
    factura = payload["factura"]
    rel = payload.get("relacion_tercero") or {}
    seller = _build_party(payload["emisor"])
    buyer = _build_party(payload["receptor"])
    admin_centres = _build_admin_centres(rel, buyer)

    lineas = []
    grouped_output: dict[tuple[str, Decimal], dict[str, Decimal]] = defaultdict(lambda: {"base": Decimal("0.00"), "amount": Decimal("0.00")})
    grouped_withheld: dict[tuple[str, Decimal], dict[str, Decimal]] = defaultdict(lambda: {"base": Decimal("0.00"), "amount": Decimal("0.00")})

    for idx, raw_line in enumerate(payload["lineas"], start=1):
        base = d2(raw_line.get("base"))
        iva_rate = d2(raw_line.get("pct_iva"))
        iva_amount = d2(raw_line.get("cuota_iva"))
        irpf_rate = d2(raw_line.get("pct_irpf"))
        irpf_amount = abs(d2(raw_line.get("cuota_irpf")))
        qty = Decimal(str(raw_line.get("unidades") or 0)).quantize(Q6, rounding=ROUND_HALF_UP)
        unit_price = q6(Decimal(str(raw_line.get("precio") or 0)))
        total_cost = q6(qty * unit_price)
        discount_amount = q6(total_cost - q6(base))
        gross_amount = q6(base)

        taxes_outputs = [_tax(iva_rate, base, iva_amount, TAX_TYPE_VAT)]
        taxes_withheld = []
        if irpf_amount:
            taxes_withheld.append(_tax(irpf_rate, base, irpf_amount, TAX_TYPE_IRPF))

        grouped_output[(TAX_TYPE_VAT, iva_rate)]["base"] += base
        grouped_output[(TAX_TYPE_VAT, iva_rate)]["amount"] += iva_amount
        if irpf_amount:
            grouped_withheld[(TAX_TYPE_IRPF, irpf_rate)]["base"] += base
            grouped_withheld[(TAX_TYPE_IRPF, irpf_rate)]["amount"] += irpf_amount

        lineas.append(
            FacturaeLine(
                description=str(raw_line.get("concepto") or factura.get("descripcion") or "").strip(),
                quantity=qty,
                unit_price=unit_price,
                total_cost=total_cost,
                gross_amount=gross_amount,
                tax_outputs=taxes_outputs,
                taxes_withheld=taxes_withheld,
                discount_amount=discount_amount,
                sequence_number=idx,
            )
        )

    taxes_outputs = [
        _tax(rate, values["base"], values["amount"], tax_type)
        for (tax_type, rate), values in sorted(grouped_output.items(), key=lambda item: item[0][1], reverse=True)
    ]
    taxes_withheld = [
        _tax(rate, values["base"], values["amount"], tax_type)
        for (tax_type, rate), values in sorted(grouped_withheld.items(), key=lambda item: item[0][1], reverse=True)
    ]

    corrective = None
    corrective_payload = payload.get("corrective")
    if corrective_payload:
        corrective = FacturaeCorrectiveData(
            invoice_number=str(corrective_payload.get("invoice_number") or "").strip(),
            invoice_series_code=str(corrective_payload.get("invoice_series_code") or "").strip(),
            reason_code=str(corrective_payload.get("reason_code") or "01").strip(),
            reason_description=str(corrective_payload.get("reason_description") or "Factura rectificativa").strip(),
        )

    return FacturaeDocument(
        invoice_number=str(factura.get("numero") or "").strip(),
        invoice_series_code=str(factura.get("serie") or "").strip(),
        issue_date=_format_date(factura.get("fecha_expedicion") or factura.get("fecha_asiento")),
        operation_date=_format_date(factura.get("fecha_operacion") or factura.get("fecha_expedicion") or factura.get("fecha_asiento")),
        description=str(factura.get("descripcion") or "").strip(),
        file_reference=str(rel.get("facturae_referencia_expediente") or "").strip()[:20],
        receiver_contract_reference=str(rel.get("facturae_referencia_contrato") or "").strip()[:20],
        receiver_transaction_reference=str(rel.get("facturae_referencia_pedido") or "").strip()[:20],
        seller=seller,
        buyer=buyer,
        administrative_centres=admin_centres,
        invoice_lines=lineas,
        taxes_outputs=taxes_outputs,
        taxes_withheld=taxes_withheld,
        total_gross_amount=d2(payload["totales"]["base"]),
        total_gross_amount_before_taxes=d2(payload["totales"]["base"]),
        total_tax_outputs=d2(payload["totales"]["iva"]),
        total_taxes_withheld=abs(d2(payload["totales"]["ret"])),
        invoice_total=d2(payload["totales"]["total"]),
        total_outstanding_amount=d2(payload["totales"]["total"]),
        total_executable_amount=d2(payload["totales"]["total"]),
        invoice_class=payload["invoice_class"],
        corrective=corrective,
    )


def _append_party(parent: ET.Element, tag: str, party: FacturaeParty, administrative_centres: list[FacturaeAdministrativeCentre] | None = None) -> None:
    node = _sub(parent, tag)
    tax_id = _sub(node, "TaxIdentification")
    _txt(tax_id, "PersonTypeCode", party.person_type)
    _txt(tax_id, "ResidenceTypeCode", party.residence_type)
    _txt(tax_id, "TaxIdentificationNumber", party.nif)

    legal = _sub(node, "LegalEntity" if party.person_type == "J" else "Individual")
    if party.person_type == "J":
        _txt(legal, "CorporateName", party.nombre)
    else:
        _txt(legal, "Name", party.nombre[:40] or party.nombre)
        _txt(legal, "FirstSurname", ".")

    address_tag = "AddressInSpain" if party.pais == "ESP" else "OverseasAddress"
    address_node = _sub(legal, address_tag)
    _txt(address_node, "Address", party.direccion)
    if address_tag == "AddressInSpain":
        _txt(address_node, "PostCode", party.cp)
        _txt(address_node, "Town", party.poblacion)
        _txt(address_node, "Province", party.provincia)
        _txt(address_node, "CountryCode", party.pais)
    else:
        _txt(address_node, "PostCodeAndTown", f"{party.cp} {party.poblacion}".strip())
        _txt(address_node, "Province", party.provincia)
        _txt(address_node, "CountryCode", party.pais)

    if party.email or party.telefono:
        contact = _sub(legal, "ContactDetails")
        if party.telefono:
            _txt(contact, "Telephone", party.telefono[:15])
        if party.email:
            _txt(contact, "ElectronicMail", party.email[:60])

    if administrative_centres:
        centres = _sub(node, "AdministrativeCentres")
        for centre in administrative_centres:
            cnode = _sub(centres, "AdministrativeCentre")
            _txt(cnode, "CentreCode", centre.centre_code[:10])
            _txt(cnode, "RoleTypeCode", centre.role_type_code)
            _txt(cnode, "Name", centre.name[:40])
            addr = _sub(cnode, "AddressInSpain" if centre.pais == "ESP" else "OverseasAddress")
            _txt(addr, "Address", centre.direccion)
            if centre.pais == "ESP":
                _txt(addr, "PostCode", centre.cp)
                _txt(addr, "Town", centre.poblacion)
                _txt(addr, "Province", centre.provincia)
                _txt(addr, "CountryCode", centre.pais)
            else:
                _txt(addr, "PostCodeAndTown", f"{centre.cp} {centre.poblacion}".strip())
                _txt(addr, "Province", centre.provincia)
                _txt(addr, "CountryCode", centre.pais)


def _append_taxes(parent: ET.Element, tag: str, taxes: list[FacturaeTaxBreakdown]) -> None:
    if not taxes and tag == "TaxesWithheld":
        return
    node = _sub(parent, tag)
    for tax in taxes:
        tnode = _sub(node, "Tax")
        _txt(tnode, "TaxTypeCode", tax.tax_type_code)
        _txt(tnode, "TaxRate", f"{tax.tax_rate:.2f}")
        _amount(tnode, "TaxableBase", tax.taxable_base)
        _amount(tnode, "TaxAmount", tax.tax_amount)


def build_facturae_xml(document: FacturaeDocument) -> str:
    ET.register_namespace("", FACTURAE_NS)
    ET.register_namespace("ds", DS_NS)
    ET.register_namespace("xsi", XSI_NS)

    root = ET.Element(
        f"{{{FACTURAE_NS}}}Facturae",
        {f"{{{XSI_NS}}}schemaLocation": SCHEMA_LOCATION},
    )
    header = _sub(root, "FileHeader")
    _txt(header, "SchemaVersion", SCHEMA_VERSION)
    _txt(header, "Modality", MODALITY_INDIVIDUAL)
    _txt(header, "InvoiceIssuerType", INVOICE_ISSUER_TYPE)
    batch = _sub(header, "Batch")
    _txt(batch, "BatchIdentifier", f"{document.invoice_series_code}{document.invoice_number}"[:20])
    _txt(batch, "InvoicesCount", "1")
    _txt(batch, "InvoiceCurrencyCode", "EUR")
    _amount(batch, "TotalInvoicesAmount", document.invoice_total)
    _amount(batch, "TotalOutstandingAmount", document.total_outstanding_amount)
    _amount(batch, "TotalExecutableAmount", document.total_executable_amount)

    parties = _sub(root, "Parties")
    _append_party(parties, "SellerParty", document.seller)
    _append_party(parties, "BuyerParty", document.buyer, document.administrative_centres)

    invoices = _sub(root, "Invoices")
    invoice = _sub(invoices, "Invoice")
    header_node = _sub(invoice, "InvoiceHeader")
    _txt(header_node, "InvoiceNumber", document.invoice_number)
    if document.invoice_series_code:
        _txt(header_node, "InvoiceSeriesCode", document.invoice_series_code)
    _txt(header_node, "InvoiceDocumentType", INVOICE_DOCUMENT_TYPE)
    _txt(header_node, "InvoiceClass", document.invoice_class)
    if document.corrective:
        corrective = _sub(header_node, "Corrective")
        _txt(corrective, "InvoiceNumber", document.corrective.invoice_number)
        if document.corrective.invoice_series_code:
            _txt(corrective, "InvoiceSeriesCode", document.corrective.invoice_series_code)
        _txt(corrective, "ReasonCode", document.corrective.reason_code)
        _txt(corrective, "ReasonDescription", document.corrective.reason_description)

    issue = _sub(invoice, "IssueData")
    _txt(issue, "IssueDate", document.issue_date)
    if document.operation_date:
        _txt(issue, "OperationDate", document.operation_date)
    _txt(issue, "InvoiceCurrencyCode", "EUR")
    _txt(issue, "TaxCurrencyCode", "EUR")
    _txt(issue, "LanguageName", "es")

    if document.receiver_transaction_reference:
        _txt(invoice, "ReceiverTransactionReference", document.receiver_transaction_reference)
    if document.file_reference:
        _txt(invoice, "FileReference", document.file_reference)
    if document.receiver_contract_reference:
        _txt(invoice, "ReceiverContractReference", document.receiver_contract_reference)

    _append_taxes(invoice, "TaxesOutputs", document.taxes_outputs)
    if document.taxes_withheld:
        _append_taxes(invoice, "TaxesWithheld", document.taxes_withheld)

    totals = _sub(invoice, "InvoiceTotals")
    _txt(totals, "TotalGrossAmount", f"{document.total_gross_amount:.2f}")
    _txt(totals, "TotalGrossAmountBeforeTaxes", f"{document.total_gross_amount_before_taxes:.2f}")
    _txt(totals, "TotalTaxOutputs", f"{document.total_tax_outputs:.2f}")
    _txt(totals, "TotalTaxesWithheld", f"{document.total_taxes_withheld:.2f}")
    _txt(totals, "InvoiceTotal", f"{document.invoice_total:.2f}")
    _txt(totals, "TotalOutstandingAmount", f"{document.total_outstanding_amount:.2f}")
    _txt(totals, "TotalExecutableAmount", f"{document.total_executable_amount:.2f}")

    items = _sub(invoice, "Items")
    for line in document.invoice_lines:
        line_node = _sub(items, "InvoiceLine")
        _txt(line_node, "SequenceNumber", line.sequence_number)
        _txt(line_node, "ItemDescription", line.description)
        _txt(line_node, "Quantity", f"{line.quantity:.6f}")
        _txt(line_node, "UnitOfMeasure", UNIT_OF_MEASURE_UNITS)
        _txt(line_node, "UnitPriceWithoutTax", f"{line.unit_price:.6f}")
        _txt(line_node, "TotalCost", f"{line.total_cost:.6f}")
        if line.discount_amount:
            discounts = _sub(line_node, "DiscountsAndRebates")
            discount = _sub(discounts, "Discount")
            _txt(discount, "DiscountReason", "Descuento aplicado")
            _txt(discount, "DiscountAmount", f"{line.discount_amount:.6f}")
        _txt(line_node, "GrossAmount", f"{line.gross_amount:.6f}")
        if line.taxes_withheld:
            _append_taxes(line_node, "TaxesWithheld", line.taxes_withheld)
        _append_taxes(line_node, "TaxesOutputs", line.tax_outputs)

    return ET.tostring(root, encoding="utf-8", xml_declaration=True).decode("utf-8")
