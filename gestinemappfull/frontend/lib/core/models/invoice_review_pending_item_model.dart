class InvoiceReviewPendingItemModel {
  const InvoiceReviewPendingItemModel({
    required this.documentId,
    required this.documentOriginalFilename,
    required this.documentCreatedAt,
    required this.ocrStatus,
    required this.ocrConfidence,
    required this.reviewStatus,
    required this.supplierNameDetected,
    required this.supplierTaxIdDetected,
    required this.invoiceNumber,
    required this.totalAmount,
  });

  final String documentId;
  final String documentOriginalFilename;
  final DateTime documentCreatedAt;
  final String? ocrStatus;
  final double? ocrConfidence;
  final String reviewStatus;
  final String? supplierNameDetected;
  final String? supplierTaxIdDetected;
  final String? invoiceNumber;
  final double? totalAmount;

  factory InvoiceReviewPendingItemModel.fromJson(Map<String, dynamic> json) {
    return InvoiceReviewPendingItemModel(
      documentId: json['document_id'] as String,
      documentOriginalFilename: json['document_original_filename'] as String,
      documentCreatedAt: DateTime.parse(json['document_created_at'] as String),
      ocrStatus: json['ocr_status'] as String?,
      ocrConfidence: (json['ocr_confidence'] as num?)?.toDouble(),
      reviewStatus: json['review_status'] as String,
      supplierNameDetected: json['supplier_name_detected'] as String?,
      supplierTaxIdDetected: json['supplier_tax_id_detected'] as String?,
      invoiceNumber: json['invoice_number'] as String?,
      totalAmount: (json['total_amount'] as num?)?.toDouble(),
    );
  }
}
