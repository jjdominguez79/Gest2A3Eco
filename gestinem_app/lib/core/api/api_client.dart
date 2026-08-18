import 'dart:typed_data';

import 'package:dio/dio.dart';

import '../config/app_config.dart';
import '../images/avatar_image.dart';

class ApiClient {
  ApiClient({
    Dio? dio,
    required String? Function() tokenProvider,
    this.onUnauthorized,
  }) : _tokenProvider = tokenProvider,
       dio = dio ?? Dio(BaseOptions(baseUrl: appConfig.apiBaseUrl)) {
    this.dio.interceptors.add(
      InterceptorsWrapper(
        onRequest: (options, handler) {
          final token = _tokenProvider();
          if (token != null && token.isNotEmpty) {
            options.headers['Authorization'] = 'Bearer $token';
          }
          handler.next(options);
        },
        onError: (error, handler) {
          if (error.response?.statusCode == 401) onUnauthorized?.call();
          handler.next(error);
        },
      ),
    );
  }

  final Dio dio;
  final String? Function() _tokenProvider;
  final void Function()? onUnauthorized;

  Future<Uint8List> download(String path) async {
    final response = await dio.get<List<int>>(
      path,
      options: Options(responseType: ResponseType.bytes),
    );
    return Uint8List.fromList(response.data ?? const []);
  }
}

String apiErrorMessage(Object error) {
  if (error is AvatarImageException) return error.message;
  if (error is DioException) {
    final data = error.response?.data;
    if (data is Map && data['detail'] != null) return data['detail'].toString();
    if (error.type == DioExceptionType.connectionError) {
      return 'No se puede conectar con Gestinem.';
    }
  }
  return 'No se ha podido completar la operación.';
}
