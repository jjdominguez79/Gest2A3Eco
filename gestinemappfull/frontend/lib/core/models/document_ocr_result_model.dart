class DocumentOcrResultModel {
  const DocumentOcrResultModel({
    required this.id,
    required this.documentId,
    required this.status,
    required this.extractedText,
    required this.extractedData,
    required this.confidence,
    required this.errorMessage,
    required this.createdAt,
    required this.updatedAt,
  });

  final String id;
  final String documentId;
  final String status;
  final String? extractedText;
  final Map<String, dynamic> extractedData;
  final double? confidence;
  final String? errorMessage;
  final DateTime createdAt;
  final DateTime updatedAt;

  factory DocumentOcrResultModel.fromJson(Map<String, dynamic> json) {
    return DocumentOcrResultModel(
      id: json['id'] as String,
      documentId: json['document_id'] as String,
      status: json['status'] as String,
      extractedText: json['extracted_text'] as String?,
      extractedData: Map<String, dynamic>.from(
        (json['extracted_data'] as Map<String, dynamic>? ?? const {}),
      ),
      confidence: (json['confidence'] as num?)?.toDouble(),
      errorMessage: json['error_message'] as String?,
      createdAt: DateTime.parse(json['created_at'] as String),
      updatedAt: DateTime.parse(json['updated_at'] as String),
    );
  }
}
