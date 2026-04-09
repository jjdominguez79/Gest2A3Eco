class CompanyAccountModel {
  const CompanyAccountModel({
    required this.id,
    required this.companyId,
    required this.accountCode,
    required this.name,
    required this.accountType,
    required this.globalThirdPartyId,
    required this.taxId,
    required this.legalName,
    required this.source,
    required this.syncStatus,
    required this.isActive,
    required this.createdAt,
    required this.updatedAt,
  });

  final String id;
  final String companyId;
  final String accountCode;
  final String name;
  final String accountType;
  final String? globalThirdPartyId;
  final String? taxId;
  final String? legalName;
  final String source;
  final String syncStatus;
  final bool isActive;
  final DateTime createdAt;
  final DateTime updatedAt;

  factory CompanyAccountModel.fromJson(Map<String, dynamic> json) {
    return CompanyAccountModel(
      id: json['id'] as String,
      companyId: json['company_id'] as String,
      accountCode: json['account_code'] as String,
      name: json['name'] as String,
      accountType: json['account_type'] as String,
      globalThirdPartyId: json['global_third_party_id'] as String?,
      taxId: json['tax_id'] as String?,
      legalName: json['legal_name'] as String?,
      source: json['source'] as String,
      syncStatus: json['sync_status'] as String,
      isActive: json['is_active'] as bool,
      createdAt: DateTime.parse(json['created_at'] as String),
      updatedAt: DateTime.parse(json['updated_at'] as String),
    );
  }
}
