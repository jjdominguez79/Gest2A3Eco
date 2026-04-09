class CompanyA3SettingsModel {
  const CompanyA3SettingsModel({
    required this.companyId,
    required this.companyName,
    required this.role,
    required this.canEdit,
    required this.a3CompanyCode,
    required this.a3Enabled,
    required this.a3ExportPath,
    required this.a3ImportMode,
    required this.updatedAt,
  });

  final String companyId;
  final String companyName;
  final String role;
  final bool canEdit;
  final String? a3CompanyCode;
  final bool a3Enabled;
  final String? a3ExportPath;
  final String? a3ImportMode;
  final DateTime updatedAt;

  factory CompanyA3SettingsModel.fromJson(Map<String, dynamic> json) {
    return CompanyA3SettingsModel(
      companyId: json['company_id'] as String,
      companyName: json['company_name'] as String,
      role: json['role'] as String,
      canEdit: json['can_edit'] as bool,
      a3CompanyCode: json['a3_company_code'] as String?,
      a3Enabled: (json['a3_enabled'] as bool?) ?? false,
      a3ExportPath: json['a3_export_path'] as String?,
      a3ImportMode: json['a3_import_mode'] as String?,
      updatedAt: DateTime.parse(json['updated_at'] as String),
    );
  }
}
