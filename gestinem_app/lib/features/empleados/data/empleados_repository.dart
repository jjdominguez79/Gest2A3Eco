import 'package:dio/dio.dart';
import 'package:file_picker/file_picker.dart';

import '../../../core/api/api_client.dart';
import '../domain/empleado_despacho.dart';

class EmpleadosRepository {
  EmpleadosRepository(this._api);

  final ApiClient _api;

  Future<List<EmpleadoDespacho>> listar() async {
    final response = await _api.dio.get<List<dynamic>>(
      '/staff/admin/directory',
    );
    return response.data!
        .map((item) => EmpleadoDespacho.fromJson(item as Map<String, dynamic>))
        .toList(growable: false);
  }

  Future<void> crear({
    required String nombre,
    required String email,
    required String rol,
    required String aliasChat,
    required bool activo,
    required Set<String> canales,
  }) => _api.dio.post<void>(
    '/staff/admin/directory',
    data: {
      'name': nombre.trim(),
      'email': email.trim(),
      'role': rol,
      'chat_alias': aliasChat.trim(),
      'active': activo,
      'channels': canales.toList()..sort(),
    },
  );

  Future<void> actualizar(
    String id, {
    required String nombre,
    required String email,
    required String rol,
    required String aliasChat,
    required bool activo,
    required Set<String> canales,
  }) => _api.dio.put<void>(
    '/staff/admin/directory/$id',
    data: {
      'name': nombre.trim(),
      'email': email.trim(),
      'role': rol,
      'chat_alias': aliasChat.trim(),
      'active': activo,
      'channels': canales.toList()..sort(),
    },
  );

  Future<void> subirAvatar(String id, PlatformFile archivo) async {
    final bytes = await archivo.readAsBytes();
    await _api.dio.put<void>(
      '/staff/admin/directory/$id/avatar',
      data: FormData.fromMap({
        'avatar': MultipartFile.fromBytes(bytes, filename: archivo.name),
      }),
    );
  }

  Future<void> eliminarAvatar(String id) =>
      _api.dio.delete<void>('/staff/admin/directory/$id/avatar');

  Future<void> revocarSesiones(String id) =>
      _api.dio.post<void>('/staff/admin/directory/$id/revoke-sessions');
}
