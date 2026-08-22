class ClientOrganization {
  const ClientOrganization({
    required this.companyCode,
    required this.name,
    required this.active,
    required this.accessStatus,
    required this.accessActive,
    required this.hasAcceptedAccess,
    required this.clientCount,
    this.privateOwnerExternalId = '',
    this.contactName = '',
    this.contactEmail = '',
    this.invitationExpiresAt,
  });

  factory ClientOrganization.fromJson(Map<String, dynamic> json) =>
      ClientOrganization(
        companyCode: json['company_code'] as String? ?? '',
        name: json['name'] as String? ?? '',
        active: json['active'] as bool? ?? true,
        accessStatus: json['client_access_status'] as String? ?? 'not_invited',
        accessActive: json['client_access_active'] as bool? ?? false,
        hasAcceptedAccess: json['has_accepted_access'] as bool? ?? false,
        clientCount: json['client_count'] as int? ?? 0,
        privateOwnerExternalId:
            json['private_owner_external_id'] as String? ?? '',
        contactName: json['contact_name'] as String? ?? '',
        contactEmail: json['contact_email'] as String? ?? '',
        invitationExpiresAt: DateTime.tryParse(
          json['invitation_expires_at'] as String? ?? '',
        )?.toLocal(),
      );

  final String companyCode;
  final String name;
  final bool active;
  final String accessStatus;
  final bool accessActive;
  final bool hasAcceptedAccess;
  final int clientCount;
  final String privateOwnerExternalId;
  final String contactName;
  final String contactEmail;
  final DateTime? invitationExpiresAt;

  String get displayName => name.isEmpty ? companyCode : name;
}
