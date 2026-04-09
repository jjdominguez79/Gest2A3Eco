class InvoiceReviewModel {
  const InvoiceReviewModel({
    required this.id,
    required this.documentId,
    required this.supplierThirdPartyId,
    required this.supplierCompanyAccountId,
    required this.supplierNameDetected,
    required this.supplierTaxIdDetected,
    required this.invoiceNumber,
    required this.invoiceDate,
    required this.taxableBase,
    required this.taxRate,
    required this.taxAmount,
    required this.totalAmount,
    required this.concept,
    required this.reviewStatus,
    required this.reviewedByUserId,
    required this.reviewedAt,
    required this.createdAt,
    required this.updatedAt,
    required this.documentOriginalFilename,
    required this.ocrText,
    required this.ocrStatus,
  });

  final String id;
  final String documentId;
  final String? supplierThirdPartyId;
  final String? supplierCompanyAccountId;
  final String? supplierNameDetected;
  final String? supplierTaxIdDetected;
  final String? invoiceNumber;
  final DateTime? invoiceDate;
  final double? taxableBase;
  final double? taxRate;
  final double? taxAmount;
  final double? totalAmount;
  final String? concept;
  final String reviewStatus;
  final String? reviewedByUserId;
  final DateTime? reviewedAt;
  final DateTime createdAt;
  final DateTime updatedAt;
  final String? documentOriginalFilename;
  final String? ocrText;
  final String? ocrStatus;

  factory InvoiceReviewModel.fromJson(Map<String, dynamic> json) {
    return InvoiceReviewModel(
      id: json['id'] as String,
      documentId: json['document_id'] as String,
      supplierThirdPartyId: json['supplier_third_party_id'] as String?,
      supplierCompanyAccountId: json['supplier_company_account_id'] as String?,
      supplierNameDetected: json['supplier_name_detected'] as String?,
      supplierTaxIdDetected: json['supplier_tax_id_detected'] as String?,
      invoiceNumber: json['invoice_number'] as String?,
      invoiceDate: json['invoice_date'] == null
          ? null
          : DateTime.parse(json['invoice_date'] as String),
      taxableBase: (json['taxable_base'] as num?)?.toDouble(),
      taxRate: (json['tax_rate'] as num?)?.toDouble(),
      taxAmount: (json['tax_amount'] as num?)?.toDouble(),
      totalAmount: (json['total_amount'] as num?)?.toDouble(),
      concept: json['concept'] as String?,
      reviewStatus: json['review_status'] as String,
      reviewedByUserId: json['reviewed_by_user_id'] as String?,
      reviewedAt: json['reviewed_at'] == null
          ? null
          : DateTime.parse(json['reviewed_at'] as String),
      createdAt: DateTime.parse(json['created_at'] as String),
      updatedAt: DateTime.parse(json['updated_at'] as String),
      documentOriginalFilename: json['document_original_filename'] as String?,
      ocrText: json['ocr_text'] as String?,
      ocrStatus: json['ocr_status'] as String?,
    );
  }
}
