/// Modelo de documento del area del cliente.
class ClientDocument {
  const ClientDocument({
    required this.id,
    required this.documentType,
    required this.displayName,
    this.description,
    this.documentDate,
    this.fiscalYear = 0,
    this.amount,
    this.currency = 'EUR',
    required this.fileName,
    this.contentType = 'application/pdf',
    this.fileSize = 0,
    required this.status,
    this.replacedById,
    this.withdrawalReason,
    this.publishedAt,
    this.isRead = false,
  });

  final String id;
  final String documentType;
  final String displayName;
  final String? description;
  final String? documentDate;
  final int fiscalYear;
  final String? amount;
  final String currency;
  final String fileName;
  final String contentType;
  final int fileSize;
  /// published | replaced | withdrawn
  final String status;
  final String? replacedById;
  final String? withdrawalReason;
  final String? publishedAt;
  final bool isRead;

  bool get isPublished => status == 'published';
  bool get isReplaced => status == 'replaced';
  bool get isWithdrawn => status == 'withdrawn';

  factory ClientDocument.fromJson(Map<String, dynamic> json) {
    return ClientDocument(
      id: json['id'] as String,
      documentType: json['document_type'] as String? ?? '',
      displayName: json['display_name'] as String? ?? '',
      description: json['description'] as String?,
      documentDate: json['document_date'] as String?,
      fiscalYear: json['fiscal_year'] as int? ?? 0,
      amount: json['amount'] as String?,
      currency: json['currency'] as String? ?? 'EUR',
      fileName: json['file_name'] as String? ?? '',
      contentType: json['content_type'] as String? ?? 'application/pdf',
      fileSize: json['file_size'] as int? ?? 0,
      status: json['status'] as String? ?? 'published',
      replacedById: json['replaced_by_id'] as String?,
      withdrawalReason: json['withdrawal_reason'] as String?,
      publishedAt: json['published_at'] as String?,
      isRead: json['is_read'] as bool? ?? false,
    );
  }
}

class DocumentListResponse {
  const DocumentListResponse({
    required this.items,
    required this.total,
    this.offset = 0,
    this.limit = 50,
  });

  final List<ClientDocument> items;
  final int total;
  final int offset;
  final int limit;

  factory DocumentListResponse.fromJson(Map<String, dynamic> json) {
    return DocumentListResponse(
      items: (json['items'] as List<dynamic>?)
              ?.map((e) => ClientDocument.fromJson(e as Map<String, dynamic>))
              .toList() ??
          [],
      total: json['total'] as int? ?? 0,
      offset: json['offset'] as int? ?? 0,
      limit: json['limit'] as int? ?? 50,
    );
  }
}
