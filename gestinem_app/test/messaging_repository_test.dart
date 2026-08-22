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

  test('administrador carga el directorio completo de clientes', () async {
    final adapter = JsonAdapter([
      {
        'company_code': 'E00006',
        'name': 'Cliente Uno',
        'active': true,
        'client_access_status': 'pending',
        'client_access_active': false,
        'has_accepted_access': false,
        'client_count': 1,
        'private_owner_external_id': 'admin',
        'contact_name': 'Ana Cliente',
        'contact_email': 'ana@example.test',
        'invitation_expires_at': '2026-08-30T10:00:00Z',
      },
    ]);
    final dio = Dio(
      BaseOptions(baseUrl: 'https://example.test/api/v1/messaging'),
    )..httpClientAdapter = adapter;
    final api = ApiClient(dio: dio, tokenProvider: () => testSession.token);

    final rows = await MessagingRepository(api).clientOrganizations();

    expect(rows.single.companyCode, 'E00006');
    expect(rows.single.accessStatus, 'pending');
    expect(rows.single.contactName, 'Ana Cliente');
    expect(rows.single.invitationExpiresAt, isNotNull);
    expect(adapter.lastRequest!.path, '/staff/admin/organizations');
  });

  test('administrador puede crear una invitacion de cliente', () async {
    final adapter = JsonAdapter({
      'invitation_id': 'invitation-1',
      'url': 'https://example.test/public/app-link/invite?token=test',
      'app_url': 'es.gestinem.app://auth/invite?token=test',
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

  test('staff carga candidatos e inicia una conversacion', () async {
    final payload = {
      'id': 'conversation-1',
      'company_code': 'E00001',
      'company_name': 'Empresa Uno',
      'kind': 'fiscal',
      'state': 'pendiente',
      'unread_count': 0,
      'updated_at': '2026-08-22T10:00:00Z',
      'started_at': null,
      'last_message': null,
    };
    final adapter = JsonAdapter([payload]);
    final dio = Dio(
      BaseOptions(baseUrl: 'https://example.test/api/v1/messaging'),
    )..httpClientAdapter = adapter;
    final api = ApiClient(dio: dio, tokenProvider: () => testSession.token);
    final repository = MessagingRepository(api);

    final targets = await repository.conversationTargets();
    expect(targets.single.companyCode, 'E00001');
    expect(adapter.lastRequest!.path, '/staff/conversation-targets');

    final startAdapter = JsonAdapter({
      ...payload,
      'started_at': '2026-08-22T10:00:00Z',
    });
    dio.httpClientAdapter = startAdapter;
    final started = await repository.startConversation('conversation-1');
    expect(started.startedAt, isNotNull);
    expect(
      startAdapter.lastRequest!.path,
      '/staff/conversations/conversation-1/start',
    );
    expect(startAdapter.lastRequest!.method, 'POST');
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

  test('consulta el historial detallado de descargas', () async {
    final adapter = JsonAdapter([
      {
        'id': 'download-1',
        'client_id': 'client-1',
        'client_name': 'María',
        'downloaded_at': '2026-08-19T08:00:00Z',
        'completed_at': '2026-08-19T08:01:00Z',
        'ip': '192.0.2.1',
        'user_agent': 'Gestinem Android',
        'sha256': 'abc123',
        'success': true,
      },
    ]);
    final dio = Dio(
      BaseOptions(baseUrl: 'https://example.test/api/v1/messaging'),
    )..httpClientAdapter = adapter;
    final api = ApiClient(dio: dio, tokenProvider: () => testSession.token);

    final rows = await MessagingRepository(api).attachmentDownloads('att-1');

    expect(rows.single.clientName, 'María');
    expect(rows.single.completedAt, isNotNull);
    expect(adapter.lastRequest!.path, '/staff/attachments/att-1/downloads');
  });

  test('administrador retira un documento indicando motivo', () async {
    final adapter = JsonAdapter({'ok': true});
    final dio = Dio(
      BaseOptions(baseUrl: 'https://example.test/api/v1/messaging'),
    )..httpClientAdapter = adapter;
    final api = ApiClient(dio: dio, tokenProvider: () => testSession.token);

    await MessagingRepository(
      api,
    ).withdrawAttachment('att-1', 'Documento incorrecto');

    expect(
      adapter.lastRequest!.path,
      '/staff/admin/attachments/att-1/withdraw',
    );
    expect(adapter.lastRequest!.method, 'POST');
    expect(adapter.lastRequest!.data, {'reason': 'Documento incorrecto'});
  });
}
