import 'dart:typed_data';

import 'package:dio/dio.dart';
import 'package:file_picker/file_picker.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:gestinem/core/api/api_client.dart';
import 'package:gestinem/features/messaging/data/messaging_repository.dart';
import 'package:gestinem/features/messaging/domain/client_organization.dart';

import 'test_helpers.dart';

final class _TestPlatformFile extends PlatformFile {
  _TestPlatformFile(this.name, List<int> bytes)
    : _bytes = Uint8List.fromList(bytes);

  @override
  final String name;
  final Uint8List _bytes;

  @override
  Uri get uri => Uri.dataFromBytes(_bytes);

  @override
  Future<int> length() async => _bytes.length;

  @override
  Future<Uint8List> readAsBytes() async => _bytes;

  @override
  Stream<Uint8List> readAsByteStream() => Stream.value(_bytes);

  @override
  dynamic noSuchMethod(Invocation invocation) => super.noSuchMethod(invocation);
}

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
        'organization_email': 'empresa@example.test',
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
    expect(rows.single.organizationEmail, 'empresa@example.test');
    expect(rows.single.invitationExpiresAt, isNotNull);
    expect(adapter.lastRequest!.path, '/staff/admin/organizations');
  });

  test('administrador puede invitar clientes de forma masiva', () async {
    final adapter = JsonAdapter({
      'invitation_count': 2,
      'email_queued_count': 2,
      'invitations': <Object>[],
    });
    final dio = Dio(
      BaseOptions(baseUrl: 'https://example.test/api/v1/messaging'),
    )..httpClientAdapter = adapter;
    final api = ApiClient(dio: dio, tokenProvider: () => testSession.token);
    const organizations = [
      ClientOrganization(
        companyCode: 'E00006',
        name: 'Cliente Uno',
        active: true,
        accessStatus: 'not_invited',
        accessActive: false,
        hasAcceptedAccess: false,
        clientCount: 0,
        organizationEmail: 'uno@example.test',
      ),
      ClientOrganization(
        companyCode: 'E00007',
        name: 'Cliente Dos',
        active: true,
        accessStatus: 'pending',
        accessActive: false,
        hasAcceptedAccess: false,
        clientCount: 1,
        contactName: 'Ana Dos',
        contactEmail: 'dos@example.test',
      ),
    ];

    final result = await MessagingRepository(api).inviteClients(organizations);

    expect(result['email_queued_count'], 2);
    expect(adapter.lastRequest!.path, '/staff/admin/invitations/batch');
    final data = adapter.lastRequest!.data as Map<String, dynamic>;
    final invitations = data['invitations'] as List<dynamic>;
    expect(invitations[0]['email'], 'uno@example.test');
    expect(invitations[1]['name'], 'Ana Dos');
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

  test('chat interno envia varios archivos multipart', () async {
    final adapter = JsonAdapter({
      'id': 'message-1',
      'conversation_id': 'thread-1',
      'author_type': 'staff',
      'author_id': 'staff-1',
      'author_name': 'Ana',
      'body': '',
      'deleted': false,
      'created_at': '2026-08-25T10:00:00Z',
      'has_attachments': true,
      'attachments': <Object>[],
    });
    final dio = Dio(
      BaseOptions(baseUrl: 'https://example.test/api/v1/messaging'),
    )..httpClientAdapter = adapter;

    await MessagingRepository(
      ApiClient(dio: dio, tokenProvider: () => 'token'),
    ).sendInternal('thread-1', '', [
      _TestPlatformFile('uno.pdf', [1, 2, 3]),
      _TestPlatformFile('dos.csv', [4, 5]),
    ]);

    expect(
      adapter.lastRequest!.path,
      '/staff/internal/threads/thread-1/messages',
    );
    final form = adapter.lastRequest!.data as FormData;
    expect(form.files.where((field) => field.key == 'files'), hasLength(2));
  });

  test('chat interno modela si la contraparte sigue activa', () async {
    final adapter = JsonAdapter([
      {
        'id': 'thread-inactive',
        'kind': 'direct',
        'channel': '',
        'title': 'Empleado inactivo',
        'unread_count': 0,
        'updated_at': '2026-08-28T10:00:00Z',
        'counterpart_id': 'employee-inactive',
        'counterpart_active': false,
      },
    ]);
    final dio = Dio(
      BaseOptions(baseUrl: 'https://example.test/api/v1/messaging'),
    )..httpClientAdapter = adapter;

    final threads = await MessagingRepository(
      ApiClient(dio: dio, tokenProvider: () => 'token'),
    ).internalThreads();

    expect(adapter.lastRequest!.path, '/staff/internal/threads');
    expect(threads.single.counterpartActive, isFalse);
  });

  test('descarga interna usa endpoint protegido de staff', () async {
    final adapter = JsonAdapter(<String, dynamic>{});
    final dio = Dio(
      BaseOptions(baseUrl: 'https://example.test/api/v1/messaging'),
    )..httpClientAdapter = adapter;

    await MessagingRepository(
      ApiClient(dio: dio, tokenProvider: () => 'token'),
    ).downloadInternalAttachment('attachment-1');

    expect(
      adapter.lastRequest!.path,
      '/staff/internal/attachments/attachment-1',
    );
    expect(adapter.lastRequest!.responseType, ResponseType.bytes);
  });
}
