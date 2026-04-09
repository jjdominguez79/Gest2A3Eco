class GlobalThirdPartyModel {
  const GlobalThirdPartyModel({
    required this.id,
    required this.thirdPartyType,
    required this.taxId,
    required this.legalName,
    required this.tradeName,
    required this.email,
    required this.phone,
    required this.address,
    required this.city,
    required this.postalCode,
    required this.country,
    required this.isActive,
    required this.createdAt,
    required this.updatedAt,
  });

  final String id;
  final String thirdPartyType;
  final String? taxId;
  final String legalName;
  final String? tradeName;
  final String? email;
  final String? phone;
  final String? address;
  final String? city;
  final String? postalCode;
  final String? country;
  final bool isActive;
  final DateTime createdAt;
  final DateTime updatedAt;

  factory GlobalThirdPartyModel.fromJson(Map<String, dynamic> json) {
    return GlobalThirdPartyModel(
      id: json['id'] as String,
      thirdPartyType: json['third_party_type'] as String,
      taxId: json['tax_id'] as String?,
      legalName: json['legal_name'] as String,
      tradeName: json['trade_name'] as String?,
      email: json['email'] as String?,
      phone: json['phone'] as String?,
      address: json['address'] as String?,
      city: json['city'] as String?,
      postalCode: json['postal_code'] as String?,
      country: json['country'] as String?,
      isActive: json['is_active'] as bool,
      createdAt: DateTime.parse(json['created_at'] as String),
      updatedAt: DateTime.parse(json['updated_at'] as String),
    );
  }
}
