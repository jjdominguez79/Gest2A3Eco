class CertificateType {
  const CertificateType({
    required this.code,
    required this.organization,
    required this.name,
    this.parameters = const [],
  });

  final String code;
  final String organization;
  final String name;
  final List<CertificateParameter> parameters;

  factory CertificateType.fromJson(Map<String, dynamic> json) =>
      CertificateType(
        code: json['code'] as String? ?? '',
        organization: json['organization'] as String? ?? '',
        name: json['name'] as String? ?? '',
        parameters: (json['parameters'] as List<dynamic>? ?? const [])
            .map(
              (item) =>
                  CertificateParameter.fromJson(item as Map<String, dynamic>),
            )
            .toList(),
      );
}

class CertificateParameter {
  const CertificateParameter({
    required this.key,
    required this.label,
    required this.type,
    required this.required,
  });

  final String key;
  final String label;
  final String type;
  final bool required;

  factory CertificateParameter.fromJson(Map<String, dynamic> json) =>
      CertificateParameter(
        key: json['key'] as String? ?? '',
        label: json['label'] as String? ?? '',
        type: json['type'] as String? ?? 'text',
        required: json['required'] as bool? ?? false,
      );
}

class CertificateRequest {
  const CertificateRequest({
    required this.id,
    required this.type,
    required this.name,
    required this.organization,
    required this.status,
    required this.createdAt,
    this.errorMessage,
    this.documentId,
    this.receiptDocumentId,
    this.certificateResult,
    this.externalReference,
    this.nextAttemptAt,
    this.submittedAt,
    this.resultSummary,
  });

  final String id;
  final String type;
  final String name;
  final String organization;
  final String status;
  final DateTime? createdAt;
  final String? errorMessage;
  final String? documentId;
  final String? receiptDocumentId;
  final String? certificateResult;
  final String? externalReference;
  final DateTime? nextAttemptAt;
  final DateTime? submittedAt;
  final String? resultSummary;

  bool get completed => status == 'completed';
  bool get cancellable => status == 'queued' && submittedAt == null;
  bool get retryable =>
      status == 'failed' ||
      status == 'needs_action' ||
      status == 'awaiting_issuance';
  bool get removable =>
      (submittedAt == null || completed) &&
      const {
        'queued',
        'completed',
        'failed',
        'needs_action',
        'cancelled',
      }.contains(status);

  factory CertificateRequest.fromJson(Map<String, dynamic> json) =>
      CertificateRequest(
        id: json['id'] as String? ?? '',
        type: json['certificate_type'] as String? ?? '',
        name: json['certificate_name'] as String? ?? '',
        organization: json['issuing_organization'] as String? ?? '',
        status: json['status'] as String? ?? 'queued',
        createdAt: DateTime.tryParse(json['created_at'] as String? ?? ''),
        errorMessage: json['error_message'] as String?,
        documentId: json['document_id'] as String?,
        receiptDocumentId: json['receipt_document_id'] as String?,
        certificateResult: json['certificate_result'] as String?,
        externalReference: json['external_reference'] as String?,
        nextAttemptAt: DateTime.tryParse(
          json['next_attempt_at'] as String? ?? '',
        ),
        submittedAt: DateTime.tryParse(json['submitted_at'] as String? ?? ''),
        resultSummary: json['result_summary'] as String?,
      );
}

class CertificateStatus {
  const CertificateStatus({
    required this.configured,
    required this.status,
    this.commonName,
    this.validUntil,
  });

  final bool configured;
  final String status;
  final String? commonName;
  final DateTime? validUntil;

  factory CertificateStatus.fromJson(Map<String, dynamic> json) =>
      CertificateStatus(
        configured: json['configured'] as bool? ?? false,
        status: json['status'] as String? ?? 'missing',
        commonName: json['common_name'] as String?,
        validUntil: DateTime.tryParse(json['valid_until'] as String? ?? ''),
      );
}
