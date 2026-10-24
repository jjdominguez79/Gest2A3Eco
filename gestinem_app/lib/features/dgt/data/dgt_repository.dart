import '../../../core/api/api_client.dart';
import '../domain/dgt_expediente.dart';

class DgtRepository {
  const DgtRepository(this._api);

  final ApiClient _api;
  static const _base = '/staff/dgt/expedientes';

  Future<List<DgtExpediente>> listar() async {
    final response = await _api.dio.get<List<dynamic>>(_base);
    return (response.data ?? const [])
        .whereType<Map>()
        .map((item) => DgtExpediente.fromJson(Map<String, dynamic>.from(item)))
        .toList(growable: false);
  }

  Future<DgtExpedienteCreado> crear({
    required String titulo,
    required String vendedorNombre,
    required String vendedorTelefono,
    required String compradorNombre,
    required String compradorTelefono,
  }) async {
    final response = await _api.dio.post<Map<String, dynamic>>(
      _base,
      data: {
        'titulo': titulo.trim(),
        'vendedor_nombre': vendedorNombre.trim(),
        'vendedor_telefono': vendedorTelefono.trim(),
        'comprador_nombre': compradorNombre.trim(),
        'comprador_telefono': compradorTelefono.trim(),
      },
    );
    return DgtExpedienteCreado.fromJson(response.data ?? const {});
  }

  Future<Map<String, DgtEnlace>> generarEnlaces(String expedienteId) async {
    final response = await _api.dio.post<Map<String, dynamic>>(
      '$_base/${Uri.encodeComponent(expedienteId)}/enlaces',
    );
    return dgtEnlacesFromJson(response.data);
  }

  Future<DgtComprobacion> comprobar(String expedienteId) async {
    final response = await _api.dio.get<Map<String, dynamic>>(
      '$_base/${Uri.encodeComponent(expedienteId)}/comprobacion',
    );
    return DgtComprobacion.fromJson(response.data ?? const {});
  }
}
