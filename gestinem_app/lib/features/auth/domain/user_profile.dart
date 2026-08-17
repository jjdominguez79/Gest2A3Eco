enum UserType { client, staff }

enum StaffRole { admin, empleado }

class UserProfile {
  const UserProfile({
    required this.id,
    required this.name,
    required this.email,
    required this.type,
    this.staffRole,
    this.channels = const [],
    this.avatarUrl = '',
  });

  factory UserProfile.fromJson(Map<String, dynamic> json, UserType type) {
    final role = json['role'] as String?;
    return UserProfile(
      id: json['id'] as String,
      name: json['name'] as String? ?? '',
      email: json['email'] as String? ?? '',
      type: type,
      staffRole: type == UserType.staff
          ? (role == 'admin' ? StaffRole.admin : StaffRole.empleado)
          : null,
      channels: (json['channels'] as List<dynamic>? ?? const [])
          .map((item) => item.toString())
          .toList(growable: false),
      avatarUrl: json['avatar_url'] as String? ?? '',
    );
  }

  final String id;
  final String name;
  final String email;
  final UserType type;
  final StaffRole? staffRole;
  final List<String> channels;
  final String avatarUrl;

  bool get isAdmin => staffRole == StaffRole.admin;

  Map<String, dynamic> toJson() => {
        'id': id,
        'name': name,
        'email': email,
        'type': type.name,
        'role': staffRole?.name,
        'channels': channels,
        'avatar_url': avatarUrl,
      };
}

class AuthSession {
  const AuthSession({required this.token, required this.profile});

  final String token;
  final UserProfile profile;

  Map<String, dynamic> toJson() => {
        'token': token,
        'profile': profile.toJson(),
      };

  factory AuthSession.fromJson(Map<String, dynamic> json) {
    final profileJson = json['profile'] as Map<String, dynamic>;
    final type = profileJson['type'] == 'staff' ? UserType.staff : UserType.client;
    return AuthSession(
      token: json['token'] as String,
      profile: UserProfile.fromJson(profileJson, type),
    );
  }
}
