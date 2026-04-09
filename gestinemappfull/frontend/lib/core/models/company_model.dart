class CompanyModel {
  const CompanyModel({
    required this.id,
    required this.name,
    required this.cif,
    required this.isActive,
    required this.createdAt,
    required this.role,
  });

  final String id;
  final String name;
  final String? cif;
  final bool isActive;
  final DateTime createdAt;
  final String role;

  factory CompanyModel.fromJson(Map<String, dynamic> json) {
    return CompanyModel(
      id: json['id'] as String,
      name: json['name'] as String,
      cif: json['cif'] as String?,
      isActive: json['is_active'] as bool,
      createdAt: DateTime.parse(json['created_at'] as String),
      role: json['role'] as String,
    );
  }
}
