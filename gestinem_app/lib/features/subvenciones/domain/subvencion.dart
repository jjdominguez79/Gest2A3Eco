class Subvencion {
  const Subvencion({
    required this.codigo,
    required this.titulo,
    required this.organo,
    required this.ambito,
    required this.alcanceNacional,
    required this.ccaa,
    required this.provincias,
    required this.etiquetas,
    required this.enlaces,
    required this.beneficiariosOficiales,
    required this.sectores,
    required this.instrumentos,
    this.fuente = 'BDNS',
    this.fuenteNombre = 'Base de Datos Nacional de Subvenciones',
    this.codigoFuente,
    this.naturaleza = 'convocatoria',
    this.municipio,
    this.fechaPublicacion,
    this.fechaInicio,
    this.fechaFin,
    this.plazoTexto,
    this.abierto,
    this.presupuesto,
    this.resumenCorto,
    this.resumen,
    this.finalidad,
    this.tipoConvocatoria,
    this.avisoLegal,
    this.mrr = false,
  });

  final String codigo;
  final String fuente;
  final String fuenteNombre;
  final String? codigoFuente;
  final String naturaleza;
  final String titulo;
  final String organo;
  final String ambito;
  final bool alcanceNacional;
  final List<String> ccaa;
  final List<String> provincias;
  final String? municipio;
  final DateTime? fechaPublicacion;
  final DateTime? fechaInicio;
  final DateTime? fechaFin;
  final String? plazoTexto;
  final bool? abierto;
  final double? presupuesto;
  final String? resumenCorto;
  final List<String> etiquetas;
  final Map<String, dynamic>? resumen;
  final String? finalidad;
  final String? tipoConvocatoria;
  final List<String> beneficiariosOficiales;
  final List<String> sectores;
  final List<String> instrumentos;
  final List<EnlaceSubvencion> enlaces;
  final String? avisoLegal;
  final bool mrr;

  factory Subvencion.fromJson(Map<String, dynamic> json) {
    List<String> strings(String key) =>
        (json[key] as List<dynamic>? ?? const [])
            .map((e) => e.toString())
            .toList();
    DateTime? fecha(String key) =>
        DateTime.tryParse(json[key]?.toString() ?? '');
    return Subvencion(
      codigo:
          json['codigo']?.toString() ?? json['codigo_bdns']?.toString() ?? '',
      fuente: json['fuente']?.toString() ?? 'BDNS',
      fuenteNombre:
          json['fuente_nombre']?.toString() ??
          'Base de Datos Nacional de Subvenciones',
      codigoFuente: json['codigo_fuente']?.toString(),
      naturaleza: json['naturaleza']?.toString() ?? 'convocatoria',
      titulo: json['titulo']?.toString() ?? '',
      organo: json['organo']?.toString() ?? '',
      ambito: json['ambito']?.toString() ?? '',
      alcanceNacional: json['alcance_nacional'] as bool? ?? false,
      ccaa: strings('ccaa'),
      provincias: strings('provincias'),
      municipio: json['municipio']?.toString(),
      fechaPublicacion: fecha('fecha_publicacion'),
      fechaInicio: fecha('fecha_inicio'),
      fechaFin: fecha('fecha_fin'),
      plazoTexto: json['plazo_texto']?.toString(),
      abierto: json['abierto'] as bool?,
      presupuesto: (json['presupuesto'] as num?)?.toDouble(),
      resumenCorto: json['resumen_corto']?.toString(),
      etiquetas: strings('etiquetas'),
      resumen: json['resumen'] is Map
          ? Map<String, dynamic>.from(json['resumen'] as Map)
          : null,
      finalidad: json['finalidad']?.toString(),
      tipoConvocatoria: json['tipo_convocatoria']?.toString(),
      beneficiariosOficiales: strings('beneficiarios_oficiales'),
      sectores: strings('sectores'),
      instrumentos: strings('instrumentos'),
      enlaces: (json['enlaces'] as List<dynamic>? ?? const [])
          .whereType<Map>()
          .map((e) => EnlaceSubvencion.fromJson(Map<String, dynamic>.from(e)))
          .toList(),
      avisoLegal: json['aviso_legal']?.toString(),
      mrr: json['mrr'] as bool? ?? false,
    );
  }
}

class EnlaceSubvencion {
  const EnlaceSubvencion({required this.titulo, required this.url});
  final String titulo;
  final String url;

  factory EnlaceSubvencion.fromJson(Map<String, dynamic> json) =>
      EnlaceSubvencion(
        titulo: json['titulo']?.toString() ?? 'Documento oficial',
        url: json['url']?.toString() ?? '',
      );
}

class TerritorioSubvencion {
  const TerritorioSubvencion({
    required this.nivel,
    required this.codigo,
    required this.nombre,
  });
  final String nivel;
  final String codigo;
  final String nombre;

  factory TerritorioSubvencion.fromJson(Map<String, dynamic> json) =>
      TerritorioSubvencion(
        nivel: json['nivel']?.toString() ?? '',
        codigo: json['codigo']?.toString() ?? '',
        nombre: json['nombre']?.toString() ?? '',
      );

  Map<String, dynamic> toJson() => {
    'nivel': nivel,
    'codigo': codigo,
    'nombre': nombre,
  };

  String get clave => '$nivel:$codigo';
}

class PreferenciasSubvenciones {
  const PreferenciasSubvenciones({
    required this.notificacionesActivas,
    required this.incluirNacionales,
    required this.usarTerritorioEmpresa,
    required this.territorioEmpresa,
    required this.suscripciones,
  });
  final bool notificacionesActivas;
  final bool incluirNacionales;
  final bool usarTerritorioEmpresa;
  final Map<String, dynamic> territorioEmpresa;
  final List<TerritorioSubvencion> suscripciones;

  factory PreferenciasSubvenciones.fromJson(Map<String, dynamic> json) =>
      PreferenciasSubvenciones(
        notificacionesActivas: json['notificaciones_activas'] as bool? ?? false,
        incluirNacionales: json['incluir_nacionales'] as bool? ?? true,
        usarTerritorioEmpresa: json['usar_territorio_empresa'] as bool? ?? true,
        territorioEmpresa: json['territorio_empresa'] is Map
            ? Map<String, dynamic>.from(json['territorio_empresa'] as Map)
            : const {},
        suscripciones: (json['suscripciones'] as List<dynamic>? ?? const [])
            .whereType<Map>()
            .map(
              (e) =>
                  TerritorioSubvencion.fromJson(Map<String, dynamic>.from(e)),
            )
            .toList(),
      );
}

class ListaSubvenciones {
  const ListaSubvenciones({required this.total, required this.elementos});
  final int total;
  final List<Subvencion> elementos;
}
