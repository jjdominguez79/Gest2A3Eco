class CompanyModel {
  const CompanyModel({
    required this.id,
    required this.name,
    required this.cif,
    required this.isActive,
    required this.a3CompanyCode,
    required this.a3Enabled,
    required this.a3ExportPath,
    required this.a3ImportMode,
    required this.createdAt,
    required this.updatedAt,
    required this.role,
  });

  final String id;
  final String name;
  final String? cif;
  final bool isActive;
  final String? a3CompanyCode;
  final bool a3Enabled;
  final String? a3ExportPath;
  final String? a3ImportMode;
  final DateTime createdAt;
  final DateTime updatedAt;
  final String role;

  factory CompanyModel.fromJson(Map<String, dynamic> json) {
    return CompanyModel(
      id: json['id'] as String,
      name: json['name'] as String,
      cif: json['cif'] as String?,
      isActive: json['is_active'] as bool,
      a3CompanyCode: json['a3_company_code'] as String?,
      a3Enabled: (json['a3_enabled'] as bool?) ?? false,
      a3ExportPath: json['a3_export_path'] as String?,
      a3ImportMode: json['a3_import_mode'] as String?,
      createdAt: DateTime.parse(json['created_at'] as String),
      updatedAt: DateTime.parse(json['updated_at'] as String),
      role: json['role'] as String,
    );
  }
}
