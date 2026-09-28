class InvitationContentVersion {
  const InvitationContentVersion({
    required this.id,
    required this.version,
    required this.status,
    required this.subject,
    required this.introText,
    required this.closingText,
    required this.manualName,
    required this.manualSize,
    required this.hasCustomManual,
    required this.manualUrl,
    this.createdBy = '',
    this.createdAt,
    this.publishedBy = '',
    this.publishedAt,
  });

  factory InvitationContentVersion.fromJson(Map<String, dynamic> json) =>
      InvitationContentVersion(
        id: json['id'] as String? ?? '',
        version: json['version'] as int? ?? 0,
        status: json['status'] as String? ?? '',
        subject: json['subject'] as String? ?? '',
        introText: json['intro_text'] as String? ?? '',
        closingText: json['closing_text'] as String? ?? '',
        manualName: json['manual_name'] as String? ?? '',
        manualSize: json['manual_size'] as int? ?? 0,
        hasCustomManual: json['has_custom_manual'] as bool? ?? false,
        manualUrl: json['manual_url'] as String? ?? '',
        createdBy: json['created_by'] as String? ?? '',
        createdAt: DateTime.tryParse(json['created_at'] as String? ?? ''),
        publishedBy: json['published_by'] as String? ?? '',
        publishedAt: DateTime.tryParse(json['published_at'] as String? ?? ''),
      );

  final String id;
  final int version;
  final String status;
  final String subject;
  final String introText;
  final String closingText;
  final String manualName;
  final int manualSize;
  final bool hasCustomManual;
  final String manualUrl;
  final String createdBy;
  final DateTime? createdAt;
  final String publishedBy;
  final DateTime? publishedAt;
}

class InvitationContentConfiguration {
  const InvitationContentConfiguration({
    required this.active,
    required this.draft,
    required this.manualUrl,
    required this.allowedVariables,
  });

  factory InvitationContentConfiguration.fromJson(Map<String, dynamic> json) {
    final draft = json['draft'];
    return InvitationContentConfiguration(
      active: InvitationContentVersion.fromJson(
        json['active'] as Map<String, dynamic>,
      ),
      draft: draft is Map<String, dynamic>
          ? InvitationContentVersion.fromJson(draft)
          : null,
      manualUrl: json['manual_url'] as String? ?? '',
      allowedVariables:
          (json['allowed_variables'] as List<dynamic>? ?? const [])
              .map((value) => value.toString())
              .toList(growable: false),
    );
  }

  final InvitationContentVersion active;
  final InvitationContentVersion? draft;
  final String manualUrl;
  final List<String> allowedVariables;

  InvitationContentVersion get editable => draft ?? active;
}
