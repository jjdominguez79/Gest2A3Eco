class DgtParteResumen {
  const DgtParteResumen({
    required this.rol,
    required this.estado,
    required this.nombre,
    required this.telefono,
  });

  factory DgtParteResumen.fromJson(String rol, Map<String, dynamic> json) =>
      DgtParteResumen(
        rol: rol,
        estado: json['estado'] as String? ?? 'pendiente',
        nombre: json['nombre'] as String? ?? '',
        telefono: json['telefono'] as String? ?? '',
      );

  final String rol;
  final String estado;
  final String nombre;
  final String telefono;
}

class DgtExpediente {
  const DgtExpediente({
    required this.id,
    required this.referencia,
    required this.titulo,
    required this.estado,
    required this.partes,
    this.matricula = '',
  });

  factory DgtExpediente.fromJson(Map<String, dynamic> json) {
    final partesJson = Map<String, dynamic>.from(
      json['partes'] as Map? ?? const {},
    );
    return DgtExpediente(
      id: json['id'] as String? ?? '',
      referencia: json['referencia'] as String? ?? '',
      titulo: json['titulo'] as String? ?? '',
      estado: json['estado'] as String? ?? 'borrador',
      partes: {
        for (final rol in const ['vendedor', 'comprador'])
          rol: DgtParteResumen.fromJson(
            rol,
            Map<String, dynamic>.from(partesJson[rol] as Map? ?? const {}),
          ),
      },
      matricula:
          (Map<String, dynamic>.from(
                json['vehiculo'] as Map? ?? const {},
              )['matricula']
              as String?) ??
          '',
    );
  }

  final String id;
  final String referencia;
  final String titulo;
  final String estado;
  final Map<String, DgtParteResumen> partes;
  final String matricula;
}

class DgtEnlace {
  const DgtEnlace({required this.rol, required this.url, this.expiresAt});

  factory DgtEnlace.fromJson(String rol, Map<String, dynamic> json) =>
      DgtEnlace(
        rol: rol,
        url: json['url'] as String? ?? '',
        expiresAt: DateTime.tryParse(json['expires_at']?.toString() ?? ''),
      );

  final String rol;
  final String url;
  final DateTime? expiresAt;
}

class DgtExpedienteCreado {
  const DgtExpedienteCreado({required this.expediente, required this.enlaces});

  factory DgtExpedienteCreado.fromJson(Map<String, dynamic> json) =>
      DgtExpedienteCreado(
        expediente: DgtExpediente.fromJson(
          Map<String, dynamic>.from(json['expediente'] as Map? ?? const {}),
        ),
        enlaces: dgtEnlacesFromJson(json['enlaces']),
      );

  final DgtExpediente expediente;
  final Map<String, DgtEnlace> enlaces;
}

Map<String, DgtEnlace> dgtEnlacesFromJson(Object? value) {
  final json = Map<String, dynamic>.from(value as Map? ?? const {});
  return {
    for (final rol in const ['vendedor', 'comprador'])
      if (json[rol] is Map)
        rol: DgtEnlace.fromJson(
          rol,
          Map<String, dynamic>.from(json[rol] as Map),
        ),
  };
}

class DgtComprobacion {
  const DgtComprobacion({
    required this.completo,
    required this.errores,
    required this.partesCompletas,
  });

  factory DgtComprobacion.fromJson(Map<String, dynamic> json) {
    final partes = Map<String, dynamic>.from(
      json['partes'] as Map? ?? const {},
    );
    return DgtComprobacion(
      completo: json['completo'] as bool? ?? false,
      errores: (json['errores'] as List<dynamic>? ?? const [])
          .map((error) => error.toString())
          .toList(growable: false),
      partesCompletas: {
        for (final rol in const ['vendedor', 'comprador'])
          rol:
              (Map<String, dynamic>.from(
                    partes[rol] as Map? ?? const {},
                  )['completo']
                  as bool?) ??
              false,
      },
    );
  }

  final bool completo;
  final List<String> errores;
  final Map<String, bool> partesCompletas;
}
