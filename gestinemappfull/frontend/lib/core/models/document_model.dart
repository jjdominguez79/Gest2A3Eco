class DocumentModel {
  const DocumentModel({
    required this.id,
    required this.companyId,
    required this.originalFilename,
    required this.storedFilename,
    required this.storagePath,
    required this.mimeType,
    required this.extension,
    required this.fileSize,
    required this.sha256Hash,
    required this.source,
    required this.documentType,
    required this.workflowStatus,
    required this.uploadedByUserId,
    required this.isActive,
    required this.createdAt,
    required this.updatedAt,
  });

  final String id;
  final String companyId;
  final String originalFilename;
  final String storedFilename;
  final String storagePath;
  final String? mimeType;
  final String? extension;
  final int fileSize;
  final String sha256Hash;
  final String source;
  final String documentType;
  final String workflowStatus;
  final String? uploadedByUserId;
  final bool isActive;
  final DateTime createdAt;
  final DateTime updatedAt;

  factory DocumentModel.fromJson(Map<String, dynamic> json) {
    return DocumentModel(
      id: json['id'] as String,
      companyId: json['company_id'] as String,
      originalFilename: json['original_filename'] as String,
      storedFilename: json['stored_filename'] as String,
      storagePath: json['storage_path'] as String,
      mimeType: json['mime_type'] as String?,
      extension: json['extension'] as String?,
      fileSize: json['file_size'] as int,
      sha256Hash: json['sha256_hash'] as String,
      source: json['source'] as String,
      documentType: json['document_type'] as String,
      workflowStatus: json['workflow_status'] as String,
      uploadedByUserId: json['uploaded_by_user_id'] as String?,
      isActive: json['is_active'] as bool,
      createdAt: DateTime.parse(json['created_at'] as String),
      updatedAt: DateTime.parse(json['updated_at'] as String),
    );
  }
}
