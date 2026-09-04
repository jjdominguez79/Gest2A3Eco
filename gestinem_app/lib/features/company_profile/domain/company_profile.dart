/// Modelo de perfil empresarial de solo lectura.
class CompanyProfile {
  const CompanyProfile({
    required this.companyCode,
    required this.name,
    this.legalName,
    this.taxId,
    this.address,
    this.postalCode,
    this.city,
    this.province,
    this.country,
    this.phone,
    this.email,
    this.logoUrl,
    this.active = true,
    this.profileSyncedAt,
  });

  final String companyCode;
  final String name;
  final String? legalName;
  final String? taxId;
  final String? address;
  final String? postalCode;
  final String? city;
  final String? province;
  final String? country;
  final String? phone;
  final String? email;
  final String? logoUrl;
  final bool active;
  final String? profileSyncedAt;

  factory CompanyProfile.fromJson(Map<String, dynamic> json) {
    return CompanyProfile(
      companyCode: json['company_code'] as String? ?? '',
      name: json['name'] as String? ?? '',
      legalName: json['legal_name'] as String?,
      taxId: json['tax_id'] as String?,
      address: json['address'] as String?,
      postalCode: json['postal_code'] as String?,
      city: json['city'] as String?,
      province: json['province'] as String?,
      country: json['country'] as String?,
      phone: json['phone'] as String?,
      email: json['email'] as String?,
      logoUrl: json['logo_url'] as String?,
      active: json['active'] as bool? ?? true,
      profileSyncedAt: json['profile_synced_at'] as String?,
    );
  }
}
