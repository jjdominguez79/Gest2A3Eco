import 'dart:async';

import 'package:dio/dio.dart';
import 'package:file_picker/file_picker.dart';

import '../../../core/api/api_client.dart';
import '../../../core/images/avatar_image.dart';

class ProfileRepository {
  ProfileRepository(this.api);
  final ApiClient api;

  Future<void> actualizarEstadosMensajes(bool mostrar) async {
    await api.dio.patch<void>(
      '/staff/me',
      data: {'mostrar_estados_mensajes': mostrar},
    );
  }

  Future<void> updateChatAlias(String alias) async {
    await api.dio.patch<void>('/staff/me', data: {'chat_alias': alias});
  }

  Future<void> actualizarPrivacidadLecturas({
    bool? clientes,
    bool? empleados,
  }) async {
    final cancelacion = CancelToken();
    await api.dio
        .patch<void>(
          '/staff/me',
          data: {
            'mostrar_lecturas_clientes': ?clientes,
            'mostrar_lecturas_empleados': ?empleados,
          },
          cancelToken: cancelacion,
          options: Options(
            sendTimeout: const Duration(seconds: 10),
            receiveTimeout: const Duration(seconds: 10),
          ),
        )
        .timeout(
          const Duration(seconds: 15),
          onTimeout: () {
            cancelacion.cancel(
              'Tiempo de espera agotado al guardar privacidad',
            );
            throw TimeoutException('No se pudo confirmar el guardado');
          },
        );
  }

  Future<String> uploadAvatar(PlatformFile file) async {
    final bytes = await prepararAvatar(file);
    final form = FormData.fromMap({
      'avatar': MultipartFile.fromBytes(bytes, filename: 'avatar.jpg'),
    });
    final response = await api.dio.put<Map<String, dynamic>>(
      '/staff/me/avatar',
      data: form,
    );
    return response.data?['avatar_url'] as String? ?? '';
  }
}
