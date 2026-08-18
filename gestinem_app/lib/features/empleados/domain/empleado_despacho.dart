class EmpleadoDespacho {
  const EmpleadoDespacho({
    required this.id,
    required this.nombre,
    required this.email,
    required this.rol,
    required this.activo,
    required this.vinculado,
    required this.aliasChat,
    required this.avatarConfigurado,
    required this.canales,
  });

  factory EmpleadoDespacho.fromJson(Map<String, dynamic> json) =>
      EmpleadoDespacho(
        id: json['id'] as String,
        nombre: json['name'] as String? ?? '',
        email: json['email'] as String? ?? '',
        rol: json['role'] as String? ?? 'empleado',
        activo: json['active'] as bool? ?? true,
        vinculado: json['linked'] as bool? ?? false,
        aliasChat: json['chat_alias'] as String? ?? '',
        avatarConfigurado: json['avatar_configured'] as bool? ?? false,
        canales: (json['channels'] as List<dynamic>? ?? const [])
            .map((item) => item.toString())
            .toSet(),
      );

  final String id;
  final String nombre;
  final String email;
  final String rol;
  final bool activo;
  final bool vinculado;
  final String aliasChat;
  final bool avatarConfigurado;
  final Set<String> canales;

  String get nombreVisible => aliasChat.trim().isEmpty ? nombre : aliasChat;
  String get avatarUrl => '/api/v1/messaging/staff/avatars/$id';
}
