class UserModel {
  const UserModel({
    required this.id,
    required this.email,
    required this.fullName,
    required this.isActive,
    required this.isSuperuser,
    required this.createdAt,
  });

  final String id;
  final String email;
  final String fullName;
  final bool isActive;
  final bool isSuperuser;
  final DateTime createdAt;

  factory UserModel.fromJson(Map<String, dynamic> json) {
    return UserModel(
      id: json['id'] as String,
      email: json['email'] as String,
      fullName: json['full_name'] as String,
      isActive: json['is_active'] as bool,
      isSuperuser: json['is_superuser'] as bool,
      createdAt: DateTime.parse(json['created_at'] as String),
    );
  }
}
