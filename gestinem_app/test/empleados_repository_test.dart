import 'package:dio/dio.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:gestinem/core/api/api_client.dart';
import 'package:gestinem/features/empleados/data/empleados_repository.dart';

import 'test_helpers.dart';

void main() {
  test('administrador lista empleados del directorio', () async {
    final adapter = JsonAdapter([
      {
        'id': 'staff-1',
        'name': 'Juan Jose',
        'email': 'juan@gestinem.es',
        'role': 'admin',
        'active': true,
        'linked': true,
        'chat_alias': 'Juan Jose',
        'avatar_configured': true,
        'channels': ['fiscal', 'laboral'],
      },
    ]);
    final dio = Dio(
      BaseOptions(baseUrl: 'https://example.test/api/v1/messaging'),
    )..httpClientAdapter = adapter;
    final repository = EmpleadosRepository(
      ApiClient(dio: dio, tokenProvider: () => 'staff-token'),
    );

    final empleados = await repository.listar();

    expect(empleados.single.nombreVisible, 'Juan Jose');
    expect(empleados.single.avatarConfigurado, isTrue);
    expect(adapter.lastRequest!.path, '/staff/admin/directory');
  });
}
