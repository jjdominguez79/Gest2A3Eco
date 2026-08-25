import 'invoice_status.dart';

/// Linea de factura online.
class InvoiceLine {
  const InvoiceLine({
    this.id,
    this.lineNumber = 1,
    this.description = '',
    this.quantity = '1',
    this.unitPrice = '0',
    this.discountPercent = '0',
    this.vatRate = '21.00',
    this.lineTotal = '0',
    this.vatAmount = '0',
  });

  final String? id;
  final int lineNumber;
  final String description;
  final String quantity;
  final String unitPrice;
  final String discountPercent;
  final String vatRate;
  final String lineTotal;
  final String vatAmount;

  factory InvoiceLine.fromJson(Map<String, dynamic> json) {
    return InvoiceLine(
      id: json['id'] as String?,
      lineNumber: json['line_number'] as int? ?? 1,
      description: json['description'] as String? ?? '',
      quantity: json['quantity'] as String? ?? '1',
      unitPrice: json['unit_price'] as String? ?? '0',
      discountPercent: json['discount_percent'] as String? ?? '0',
      vatRate: json['vat_rate'] as String? ?? '21.00',
      lineTotal: json['line_total'] as String? ?? '0',
      vatAmount: json['vat_amount'] as String? ?? '0',
    );
  }

  Map<String, dynamic> toJson() => {
        'description': description,
        'quantity': quantity,
        'unit_price': unitPrice,
        'discount_percent': discountPercent,
        'vat_rate': vatRate,
      };
}

/// Cliente/deudor para facturacion.
class InvoiceCustomer {
  const InvoiceCustomer({
    required this.id,
    required this.taxId,
    required this.legalName,
    this.address = '',
    this.postalCode = '',
    this.city = '',
    this.province = '',
    this.country = 'ES',
    this.email = '',
    this.phone = '',
    this.defaultVatRate = '21.00',
    this.active = true,
  });

  final String id;
  final String taxId;
  final String legalName;
  final String address;
  final String postalCode;
  final String city;
  final String province;
  final String country;
  final String email;
  final String phone;
  final String defaultVatRate;
  final bool active;

  factory InvoiceCustomer.fromJson(Map<String, dynamic> json) {
    return InvoiceCustomer(
      id: json['id'] as String,
      taxId: json['tax_id'] as String? ?? '',
      legalName: json['legal_name'] as String? ?? '',
      address: json['address'] as String? ?? '',
      postalCode: json['postal_code'] as String? ?? '',
      city: json['city'] as String? ?? '',
      province: json['province'] as String? ?? '',
      country: json['country'] as String? ?? 'ES',
      email: json['email'] as String? ?? '',
      phone: json['phone'] as String? ?? '',
      defaultVatRate: json['default_vat_rate'] as String? ?? '21.00',
      active: json['active'] as bool? ?? true,
    );
  }
}

/// Factura online.
class ClientInvoice {
  const ClientInvoice({
    required this.id,
    required this.fiscalYear,
    this.seriesCode = 'WEB',
    this.invoiceNumber,
    this.invoiceDate,
    required this.status,
    required this.customerId,
    this.subtotal = '0',
    this.totalVat = '0',
    this.withholdingRate = '0',
    this.withholdingAmount = '0',
    this.total = '0',
    this.currency = 'EUR',
    this.paymentMethod = '',
    this.notes = '',
    this.recipientEmail = '',
    this.createdAt,
    this.issuedAt,
    this.lines = const [],
  });

  final String id;
  final int fiscalYear;
  final String seriesCode;
  final int? invoiceNumber;
  final String? invoiceDate;
  final InvoiceStatus status;
  final String customerId;
  final String subtotal;
  final String totalVat;
  final String withholdingRate;
  final String withholdingAmount;
  final String total;
  final String currency;
  final String paymentMethod;
  final String notes;
  final String recipientEmail;
  final String? createdAt;
  final String? issuedAt;
  final List<InvoiceLine> lines;

  String get displayNumber {
    if (invoiceNumber == null) return 'Borrador';
    return '$seriesCode-${invoiceNumber.toString().padLeft(6, '0')}';
  }

  factory ClientInvoice.fromJson(Map<String, dynamic> json) {
    return ClientInvoice(
      id: json['id'] as String,
      fiscalYear: json['fiscal_year'] as int? ?? DateTime.now().year,
      seriesCode: json['series_code'] as String? ?? 'WEB',
      invoiceNumber: json['invoice_number'] as int?,
      invoiceDate: json['invoice_date'] as String?,
      status: InvoiceStatus.fromString(json['status'] as String? ?? 'draft'),
      customerId: json['customer_id'] as String? ?? '',
      subtotal: json['subtotal'] as String? ?? '0',
      totalVat: json['total_vat'] as String? ?? '0',
      withholdingRate: json['withholding_rate'] as String? ?? '0',
      withholdingAmount: json['withholding_amount'] as String? ?? '0',
      total: json['total'] as String? ?? '0',
      currency: json['currency'] as String? ?? 'EUR',
      paymentMethod: json['payment_method'] as String? ?? '',
      notes: json['notes'] as String? ?? '',
      recipientEmail: json['recipient_email'] as String? ?? '',
      createdAt: json['created_at'] as String?,
      issuedAt: json['issued_at'] as String?,
      lines: (json['lines'] as List<dynamic>?)
              ?.map((e) => InvoiceLine.fromJson(e as Map<String, dynamic>))
              .toList() ??
          const [],
    );
  }
}
