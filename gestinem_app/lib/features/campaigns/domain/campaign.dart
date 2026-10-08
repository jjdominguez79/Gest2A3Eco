class Campaign {
  const Campaign({
    required this.id,
    required this.name,
    required this.status,
    required this.recipientCount,
  });
  factory Campaign.fromJson(Map<String, dynamic> json) => Campaign(
    id: json['id'] as String,
    name: json['name'] as String,
    status: json['status'] as String,
    recipientCount: json['recipient_count'] as int? ?? 0,
  );
  final String id;
  final String name;
  final String status;
  final int recipientCount;
}

class CampaignClientTarget {
  const CampaignClientTarget({
    required this.id,
    required this.name,
    required this.company,
    this.email = '',
    this.companyCode = '',
  });
  factory CampaignClientTarget.fromJson(Map<String, dynamic> json) =>
      CampaignClientTarget(
        id: json['id'] as String,
        name: json['name'] as String? ?? '',
        company: json['company_name'] as String? ?? '',
        email: json['email'] as String? ?? '',
        companyCode: json['company_code'] as String? ?? '',
      );
  final String id;
  final String name;
  final String company;
  final String email;
  final String companyCode;

  String get displayName => name.isEmpty ? company : name;
}
