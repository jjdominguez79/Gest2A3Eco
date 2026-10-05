import '../../../core/api/api_client.dart';
import '../domain/subvencion.dart';

class SubvencionesAdminRepository {
  const SubvencionesAdminRepository(this._api);
  final ApiClient _api;

  static const _base = '/staff/admin/subvenciones';

  Future<DashboardSubvencionesAdmin> dashboard() async {
    final response = await _api.dio.get<Map<String, dynamic>>(
      '$_base/dashboard',
    );
    return DashboardSubvencionesAdmin.fromJson(response.data ?? const {});
  }

  Future<ListaSubvenciones> listar({
    String consulta = '',
    String estado = 'en_vigor',
    String visibilidad = 'visibles',
    String fuente = '',
    int pagina = 0,
  }) async {
    final response = await _api.dio.get<Map<String, dynamic>>(
      _base,
      queryParameters: {
        'q': consulta.trim(),
        'estado': estado,
        'visibilidad': visibilidad,
        'fuente': fuente,
        'pagina': pagina,
        'tamano': 50,
      },
    );
    final json = response.data ?? const {};
    return ListaSubvenciones(
      total: json['total'] as int? ?? 0,
      elementos: (json['elementos'] as List<dynamic>? ?? const [])
          .whereType<Map>()
          .map((item) => Subvencion.fromJson(Map<String, dynamic>.from(item)))
          .toList(growable: false),
    );
  }

  Future<Subvencion> detalle(String codigo) async {
    final response = await _api.dio.get<Map<String, dynamic>>(
      '$_base/${Uri.encodeComponent(codigo)}',
    );
    return Subvencion.fromJson(response.data ?? const {});
  }

  Future<Subvencion> editar(
    String codigo, {
    bool? visible,
    bool? revisada,
    bool rehacerResumen = false,
  }) async {
    final changes = <String, dynamic>{};
    if (visible != null) changes['visible'] = visible;
    if (revisada != null) changes['revisada'] = revisada;
    if (rehacerResumen) changes['rehacer_resumen'] = true;
    final response = await _api.dio.patch<Map<String, dynamic>>(
      '$_base/${Uri.encodeComponent(codigo)}',
      data: changes,
    );
    return Subvencion.fromJson(response.data ?? const {});
  }

  Future<void> sincronizar() async {
    await _api.dio.post<void>('$_base/sincronizar');
  }
}
