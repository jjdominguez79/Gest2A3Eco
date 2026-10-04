import '../../../core/api/api_client.dart';
import '../domain/subvencion.dart';

class SubvencionesRepository {
  const SubvencionesRepository(this._api);
  final ApiClient _api;

  Future<ListaSubvenciones> listar({
    required bool paraMi,
    String consulta = '',
    int pagina = 0,
  }) async {
    final response = await _api.dio.get<Map<String, dynamic>>(
      '/client/subvenciones',
      queryParameters: {
        'para_mi': paraMi,
        'vigentes': true,
        'q': consulta.trim(),
        'pagina': pagina,
        'tamano': 50,
      },
    );
    final json = response.data ?? const {};
    return ListaSubvenciones(
      total: json['total'] as int? ?? 0,
      elementos: (json['elementos'] as List<dynamic>? ?? const [])
          .whereType<Map>()
          .map((e) => Subvencion.fromJson(Map<String, dynamic>.from(e)))
          .toList(),
    );
  }

  Future<Subvencion> detalle(String codigo) async {
    final response = await _api.dio.get<Map<String, dynamic>>(
      '/client/subvenciones/${Uri.encodeComponent(codigo)}',
    );
    return Subvencion.fromJson(response.data ?? const {});
  }

  Future<PreferenciasSubvenciones> preferencias() async {
    final response = await _api.dio.get<Map<String, dynamic>>(
      '/client/subvenciones/preferencias',
    );
    return PreferenciasSubvenciones.fromJson(response.data ?? const {});
  }

  Future<PreferenciasSubvenciones> guardarPreferencias({
    required bool notificacionesActivas,
    required bool incluirNacionales,
    required bool usarTerritorioEmpresa,
    required List<TerritorioSubvencion> suscripciones,
  }) async {
    final response = await _api.dio.put<Map<String, dynamic>>(
      '/client/subvenciones/preferencias',
      data: {
        'notificaciones_activas': notificacionesActivas,
        'incluir_nacionales': incluirNacionales,
        'usar_territorio_empresa': usarTerritorioEmpresa,
        'suscripciones': suscripciones.map((e) => e.toJson()).toList(),
      },
    );
    return PreferenciasSubvenciones.fromJson(response.data ?? const {});
  }

  Future<List<TerritorioSubvencion>> territorios({String consulta = ''}) async {
    final response = await _api.dio.get<List<dynamic>>(
      '/client/subvenciones/territorios',
      queryParameters: {'q': consulta.trim()},
    );
    return (response.data ?? const [])
        .whereType<Map>()
        .map((e) => TerritorioSubvencion.fromJson(Map<String, dynamic>.from(e)))
        .toList();
  }
}
