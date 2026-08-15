import 'package:dio/dio.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:gestinem/core/api/api_client.dart';
import 'package:gestinem/features/auth/presentation/auth_controller.dart';
import 'package:gestinem/features/messaging/presentation/messaging_providers.dart';

import 'test_helpers.dart';

void main() {
  test('provider principal expone conversaciones del repository', () async {
    final adapter = JsonAdapter([
      {
        'id': 'c1', 'company_code': 'E1', 'company_name': 'Empresa',
        'kind': 'laboral', 'state': 'pendiente', 'unread_count': 0,
        'updated_at': '2026-08-15T10:00:00Z', 'last_message': null,
      }
    ]);
    final dio = Dio(BaseOptions(baseUrl: 'https://example.test'))..httpClientAdapter = adapter;
    final container = ProviderContainer(overrides: [
      sessionProvider.overrideWith((ref) => FakeSessionController(ref)),
      apiClientProvider.overrideWithValue(ApiClient(dio: dio, tokenProvider: () => testSession.token)),
    ]);
    addTearDown(container.dispose);

    final conversations = await container.read(conversationsProvider.future);
    expect(conversations.single.title, 'Empresa');
  });
}
