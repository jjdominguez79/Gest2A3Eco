class AccountingPendingItemModel {
  const AccountingPendingItemModel({
    required this.documentId,
    required this.invoiceReviewId,
    required this.originalFilename,
    required this.supplierName,
    required this.supplierTaxId,
    required this.invoiceNumber,
    required this.invoiceDate,
    required this.totalAmount,
    required this.companyAccountCode,
    required this.workflowStatus,
    required this.latestBatchId,
    required this.latestBatchStatus,
  });

  final String documentId;
  final String invoiceReviewId;
  final String originalFilename;
  final String? supplierName;
  final String? supplierTaxId;
  final String? invoiceNumber;
  final DateTime? invoiceDate;
  final double? totalAmount;
  final String? companyAccountCode;
  final String workflowStatus;
  final String? latestBatchId;
  final String? latestBatchStatus;

  factory AccountingPendingItemModel.fromJson(Map<String, dynamic> json) {
    return AccountingPendingItemModel(
      documentId: json['document_id'] as String,
      invoiceReviewId: json['invoice_review_id'] as String,
      originalFilename: json['original_filename'] as String,
      supplierName: json['supplier_name'] as String?,
      supplierTaxId: json['supplier_tax_id'] as String?,
      invoiceNumber: json['invoice_number'] as String?,
      invoiceDate: json['invoice_date'] == null
          ? null
          : DateTime.parse(json['invoice_date'] as String),
      totalAmount: (json['total_amount'] as num?)?.toDouble(),
      companyAccountCode: json['company_account_code'] as String?,
      workflowStatus: json['workflow_status'] as String,
      latestBatchId: json['latest_batch_id'] as String?,
      latestBatchStatus: json['latest_batch_status'] as String?,
    );
  }
}

class AccountingBatchItemModel {
  const AccountingBatchItemModel({
    required this.id,
    required this.batchId,
    required this.documentId,
    required this.invoiceReviewId,
    required this.status,
    required this.errorMessage,
    required this.createdAt,
    required this.originalFilename,
    required this.invoiceNumber,
    required this.workflowStatus,
  });

  final String id;
  final String batchId;
  final String documentId;
  final String? invoiceReviewId;
  final String status;
  final String? errorMessage;
  final DateTime createdAt;
  final String? originalFilename;
  final String? invoiceNumber;
  final String? workflowStatus;

  factory AccountingBatchItemModel.fromJson(Map<String, dynamic> json) {
    return AccountingBatchItemModel(
      id: json['id'] as String,
      batchId: json['batch_id'] as String,
      documentId: json['document_id'] as String,
      invoiceReviewId: json['invoice_review_id'] as String?,
      status: json['status'] as String,
      errorMessage: json['error_message'] as String?,
      createdAt: DateTime.parse(json['created_at'] as String),
      originalFilename: json['original_filename'] as String?,
      invoiceNumber: json['invoice_number'] as String?,
      workflowStatus: json['workflow_status'] as String?,
    );
  }
}

class AccountingBatchModel {
  const AccountingBatchModel({
    required this.id,
    required this.companyId,
    required this.batchType,
    required this.status,
    required this.a3CompanyCodeSnapshot,
    required this.fileName,
    required this.filePath,
    required this.fileHash,
    required this.createdByUserId,
    required this.generatedByUserId,
    required this.downloadedByUserId,
    required this.exportedByUserId,
    required this.createdByName,
    required this.generatedByName,
    required this.downloadedByName,
    required this.exportedByName,
    required this.createdAt,
    required this.generatedAt,
    required this.downloadedAt,
    required this.exportedAt,
    required this.totalDocuments,
    required this.totalEntries,
    required this.notes,
    required this.errorMessage,
    required this.items,
  });

  final String id;
  final String companyId;
  final String batchType;
  final String status;
  final String? a3CompanyCodeSnapshot;
  final String? fileName;
  final String? filePath;
  final String? fileHash;
  final String? createdByUserId;
  final String? generatedByUserId;
  final String? downloadedByUserId;
  final String? exportedByUserId;
  final String? createdByName;
  final String? generatedByName;
  final String? downloadedByName;
  final String? exportedByName;
  final DateTime createdAt;
  final DateTime? generatedAt;
  final DateTime? downloadedAt;
  final DateTime? exportedAt;
  final int totalDocuments;
  final int totalEntries;
  final String? notes;
  final String? errorMessage;
  final List<AccountingBatchItemModel> items;

  factory AccountingBatchModel.fromJson(Map<String, dynamic> json) {
    return AccountingBatchModel(
      id: json['id'] as String,
      companyId: json['company_id'] as String,
      batchType: json['batch_type'] as String,
      status: json['status'] as String,
      a3CompanyCodeSnapshot: json['a3_company_code_snapshot'] as String?,
      fileName: json['file_name'] as String?,
      filePath: json['file_path'] as String?,
      fileHash: json['file_hash'] as String?,
      createdByUserId: json['created_by_user_id'] as String?,
      generatedByUserId: json['generated_by_user_id'] as String?,
      downloadedByUserId: json['downloaded_by_user_id'] as String?,
      exportedByUserId: json['exported_by_user_id'] as String?,
      createdByName: json['created_by_name'] as String?,
      generatedByName: json['generated_by_name'] as String?,
      downloadedByName: json['downloaded_by_name'] as String?,
      exportedByName: json['exported_by_name'] as String?,
      createdAt: DateTime.parse(json['created_at'] as String),
      generatedAt: json['generated_at'] == null
          ? null
          : DateTime.parse(json['generated_at'] as String),
      downloadedAt: json['downloaded_at'] == null
          ? null
          : DateTime.parse(json['downloaded_at'] as String),
      exportedAt: json['exported_at'] == null
          ? null
          : DateTime.parse(json['exported_at'] as String),
      totalDocuments: (json['total_documents'] as num?)?.toInt() ?? 0,
      totalEntries: (json['total_entries'] as num?)?.toInt() ?? 0,
      notes: json['notes'] as String?,
      errorMessage: json['error_message'] as String?,
      items: (json['items'] as List<dynamic>? ?? const [])
          .map(
            (item) =>
                AccountingBatchItemModel.fromJson(item as Map<String, dynamic>),
          )
          .toList(),
    );
  }
}
