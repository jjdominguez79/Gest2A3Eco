import 'package:dio/dio.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:gestinem/core/api/api_client.dart';
import 'package:gestinem/features/messaging/data/messaging_repository.dart';

import 'test_helpers.dart';

void main() {
  test('repository carga conversaciones cliente con token Bearer', () async {
    final adapter = JsonAdapter([
      {
        'id': 'conversation-1',
        'company_code': 'E00001',
        'company_name': 'Empresa Uno',
        'kind': 'fiscal',
        'state': 'pendiente',
        'unread_count': 2,
        'updated_at': '2026-08-15T10:00:00Z',
        'last_message': null,
      },
    ]);
    final dio = Dio(BaseOptions(baseUrl: 'https://example.test'))
      ..httpClientAdapter = adapter;
    final api = ApiClient(dio: dio, tokenProvider: () => testSession.token);
    final rows = await MessagingRepository(api).conversations(testProfile);

    expect(rows.single.companyCode, 'E00001');
    expect(rows.single.unreadCount, 2);
    expect(adapter.lastRequest!.path, '/client/conversations');
    expect(adapter.lastRequest!.headers['Authorization'], 'Bearer test-token');
  });

  test(
    'repository usa rutas relativas para la conversacion unificada',
    () async {
      final adapter = JsonAdapter({
        'channel_ids': <String, dynamic>{},
        'unread_count': 0,
        'last_message': null,
      });
      final dio = Dio(
        BaseOptions(baseUrl: 'https://example.test/api/v1/messaging'),
      )..httpClientAdapter = adapter;
      final api = ApiClient(dio: dio, tokenProvider: () => testSession.token);

      await MessagingRepository(api).unifiedConversation();

      expect(adapter.lastRequest!.path, '/client/unified-conversation');
    },
  );

  test('repository usa ruta relativa para los mensajes unificados', () async {
    final adapter = JsonAdapter(<Object>[]);
    final dio = Dio(
      BaseOptions(baseUrl: 'https://example.test/api/v1/messaging'),
    )..httpClientAdapter = adapter;
    final api = ApiClient(dio: dio, tokenProvider: () => testSession.token);

    final rows = await MessagingRepository(api).unifiedMessages();

    expect(rows, isEmpty);
    expect(adapter.lastRequest!.path, '/client/unified-messages');
  });

  test('administrador puede desactivar el acceso de un cliente', () async {
    final adapter = JsonAdapter({'status': 'disabled', 'active': false});
    final dio = Dio(
      BaseOptions(baseUrl: 'https://example.test/api/v1/messaging'),
    )..httpClientAdapter = adapter;
    final api = ApiClient(dio: dio, tokenProvider: () => testSession.token);

    await MessagingRepository(api).setClientAccess('E00006', false);

    expect(
      adapter.lastRequest!.path,
      '/staff/admin/organizations/E00006/client-access',
    );
    expect(adapter.lastRequest!.method, 'PATCH');
    expect(adapter.lastRequest!.data, {'active': false});
  });

  test('administrador puede crear una invitacion de cliente', () async {
    final adapter = JsonAdapter({
      'invitation_id': 'invitation-1',
      'url': 'es.gestinem.app://auth/accept-invite?token=test',
      'email_queued': true,
      'expires_at': '2026-08-20T10:00:00Z',
    });
    final dio = Dio(
      BaseOptions(baseUrl: 'https://example.test/api/v1/messaging'),
    )..httpClientAdapter = adapter;
    final api = ApiClient(dio: dio, tokenProvider: () => testSession.token);

    final result = await MessagingRepository(api).inviteClient(
      companyCode: 'E00006',
      name: 'Ana Cliente',
      email: 'ana@example.test',
    );

    expect(result['email_queued'], isTrue);
    expect(adapter.lastRequest!.path, '/staff/admin/invitations');
    expect(adapter.lastRequest!.method, 'POST');
    expect(adapter.lastRequest!.data, {
      'company_code': 'E00006',
      'name': 'Ana Cliente',
      'email': 'ana@example.test',
      'send_email': true,
    });
  });

  test('consulta la ultima version publicada para Windows', () async {
    final adapter = JsonAdapter({
      'platform': 'windows',
      'latest_version': '0.1.1',
      'latest_build': 11,
      'minimum_build': 1,
    });
    final dio = Dio(
      BaseOptions(baseUrl: 'https://example.test/api/v1/messaging'),
    )..httpClientAdapter = adapter;
    final api = ApiClient(dio: dio, tokenProvider: () => testSession.token);

    final result = await MessagingRepository(api).latestAppVersion('windows');

    expect(result['latest_build'], 11);
    expect(adapter.lastRequest!.path, '/public/app-version');
    expect(adapter.lastRequest!.queryParameters, {'platform': 'windows'});
  });
}
