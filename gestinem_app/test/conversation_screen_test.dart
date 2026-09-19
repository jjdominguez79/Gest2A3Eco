import 'dart:convert';
import 'dart:typed_data';

import 'package:dio/dio.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:go_router/go_router.dart';
import 'package:gestinem/features/auth/presentation/auth_controller.dart';
import 'package:gestinem/features/messaging/domain/conversation.dart';
import 'package:gestinem/features/messaging/domain/message.dart';
import 'package:gestinem/features/messaging/presentation/conversation_screen.dart';
import 'package:gestinem/features/messaging/presentation/messaging_providers.dart';
import 'package:gestinem/core/api/api_client.dart';

import 'test_helpers.dart';

void main() {
  test('solo considera propio un mensaje del mismo tipo y usuario', () {
    final sameTypeOtherUser = Message(
      id: 'm-other',
      conversationId: 't1',
      authorType: 'client',
      authorId: 'client-2',
      authorName: 'Otra persona',
      authorAvatarUrl: '',
      body: 'Mensaje ajeno',
      createdAt: DateTime(2026, 8, 15),
      deleted: false,
    );
    final own = Message(
      id: 'm-own',
      conversationId: 't1',
      authorType: 'client',
      authorId: testProfile.id,
      authorName: testProfile.name,
      authorAvatarUrl: '',
      body: 'Mensaje propio',
      createdAt: DateTime(2026, 8, 15),
      deleted: false,
    );

    expect(messageBelongsToProfile(sameTypeOtherUser, testProfile), isFalse);
    expect(messageBelongsToProfile(own, testProfile), isTrue);
  });

  testWidgets('conversacion renderiza historial y compositor', (tester) async {
    final adapter = JsonAdapter(<String, dynamic>{});
    final dio = Dio(BaseOptions(baseUrl: 'https://example.test'))
      ..httpClientAdapter = adapter;
    final message = Message(
      id: 'm1',
      conversationId: 't1',
      authorType: 'staff',
      authorId: 'staff-1',
      authorName: 'Ana',
      authorAvatarUrl: '',
      body: 'Buenos dias',
      createdAt: DateTime(2026, 8, 15),
      deleted: false,
    );
    final ownMessage = Message(
      id: 'm2',
      conversationId: 't1',
      authorType: 'client',
      authorId: testProfile.id,
      authorName: testProfile.name,
      authorAvatarUrl: '',
      body: 'Mensaje propio',
      createdAt: DateTime(2026, 8, 15, 12),
      deleted: false,
      estadoEnvio: 'read',
      lecturas: 2,
      destinatarios: 2,
    );
    await tester.pumpWidget(
      ProviderScope(
        overrides: [
          sessionProvider.overrideWith((ref) => FakeSessionController(ref)),
          apiClientProvider.overrideWithValue(
            ApiClient(dio: dio, tokenProvider: () => testSession.token),
          ),
          internalThreadsProvider.overrideWith(
            (ref) async => const [
              InternalThread(
                id: 't1',
                kind: 'direct',
                channel: '',
                title: 'Analía Pérez',
                unreadCount: 0,
              ),
            ],
          ),
          internalMessagesProvider.overrideWith(
            (ref, id) async => [message, ownMessage],
          ),
        ],
        child: const MaterialApp(
          home: Scaffold(
            body: ConversationView(
              conversationId: 't1',
              internal: true,
              showInternalHeader: true,
            ),
          ),
        ),
      ),
    );
    await tester.pump();
    await tester.pump();

    expect(find.text('Analía Pérez'), findsOneWidget);
    expect(find.text('Chat directo'), findsOneWidget);
    expect(find.text('Buenos dias'), findsOneWidget);
    expect(find.text('Mensaje propio'), findsOneWidget);
    expect(find.textContaining('Leido'), findsNothing);
    expect(find.byKey(const Key('message-composer')), findsOneWidget);
    expect(find.byKey(const Key('record-voice-note')), findsOneWidget);
    expect(find.byKey(const Key('send-message')), findsOneWidget);
    await tester.enterText(
      find.byKey(const Key('message-composer')),
      'hola. segundo mensaje',
    );
    expect(find.text('Hola. Segundo mensaje'), findsOneWidget);
    await tester.pumpAndSettle();
    expect(adapter.lastRequest?.path, '/staff/internal/threads/t1/read');
  });

  testWidgets('volver desde un chat interno abre la lista de inicio', (
    tester,
  ) async {
    final dio = Dio(BaseOptions(baseUrl: 'https://example.test'))
      ..httpClientAdapter = JsonAdapter(<String, dynamic>{});
    final router = GoRouter(
      initialLocation: '/internal/t1',
      routes: [
        GoRoute(
          path: '/',
          builder: (_, _) => const Scaffold(body: Text('Lista de inicio')),
        ),
        GoRoute(
          path: '/internal/:id',
          builder: (_, state) => ConversationScreen(
            conversationId: state.pathParameters['id']!,
            internal: true,
          ),
        ),
      ],
    );
    await tester.pumpWidget(
      ProviderScope(
        overrides: [
          sessionProvider.overrideWith((ref) => FakeSessionController(ref)),
          apiClientProvider.overrideWithValue(
            ApiClient(dio: dio, tokenProvider: () => testSession.token),
          ),
          internalThreadsProvider.overrideWith(
            (ref) async => const [
              InternalThread(
                id: 't1',
                kind: 'direct',
                channel: '',
                title: 'Analía Pérez',
                unreadCount: 0,
              ),
            ],
          ),
          internalMessagesProvider.overrideWith((ref, id) async => []),
        ],
        child: MaterialApp.router(routerConfig: router),
      ),
    );
    await tester.pumpAndSettle();

    await tester.tap(find.byIcon(Icons.arrow_back));
    await tester.pumpAndSettle();

    expect(find.text('Lista de inicio'), findsOneWidget);
  });

  testWidgets('al abrir una conversacion muestra los mensajes del final', (
    tester,
  ) async {
    final dio = Dio(BaseOptions(baseUrl: 'https://example.test'))
      ..httpClientAdapter = _ConversationAdapter();

    await tester.pumpWidget(
      ProviderScope(
        overrides: [
          sessionProvider.overrideWith((ref) => FakeSessionController(ref)),
          apiClientProvider.overrideWithValue(
            ApiClient(dio: dio, tokenProvider: () => testSession.token),
          ),
          internalThreadsProvider.overrideWith(
            (ref) async => const [
              InternalThread(
                id: 't1',
                kind: 'direct',
                channel: '',
                title: 'Analía Pérez',
                unreadCount: 0,
              ),
            ],
          ),
        ],
        child: const MaterialApp(
          home: Scaffold(
            body: ConversationView(conversationId: 't1', internal: true),
          ),
        ),
      ),
    );
    await tester.pumpAndSettle();

    final messageScroll = tester.state<ScrollableState>(
      find
          .descendant(
            of: find.byKey(const Key('message-list')),
            matching: find.byType(Scrollable),
          )
          .first,
    );
    expect(messageScroll.position.maxScrollExtent, greaterThan(0));
    expect(find.text('Mensaje anterior 19').hitTestable(), findsOneWidget);
    expect(
      messageScroll.position.pixels,
      closeTo(messageScroll.position.minScrollExtent, 0.5),
    );
  });

  testWidgets(
    'al enviar mantiene el foco y muestra el mensaje nuevo al final',
    (tester) async {
      final adapter = _ConversationAdapter();
      final dio = Dio(BaseOptions(baseUrl: 'https://example.test'))
        ..httpClientAdapter = adapter;

      await tester.pumpWidget(
        ProviderScope(
          overrides: [
            sessionProvider.overrideWith((ref) => FakeSessionController(ref)),
            apiClientProvider.overrideWithValue(
              ApiClient(dio: dio, tokenProvider: () => testSession.token),
            ),
            internalThreadsProvider.overrideWith(
              (ref) async => const [
                InternalThread(
                  id: 't1',
                  kind: 'direct',
                  channel: '',
                  title: 'Analía Pérez',
                  unreadCount: 0,
                ),
              ],
            ),
          ],
          child: const MaterialApp(
            home: Scaffold(
              body: ConversationView(conversationId: 't1', internal: true),
            ),
          ),
        ),
      );
      await tester.pumpAndSettle();

      const composerKey = Key('message-composer');
      // Enviar desde el historial tambien debe volver al mensaje mas reciente.
      await tester.drag(
        find.byKey(const Key('message-list')),
        const Offset(0, 900),
      );
      await tester.pumpAndSettle();
      await tester.tap(find.byKey(composerKey));
      await tester.enterText(find.byKey(composerKey), 'mensaje nuevo');
      await tester.tap(find.byKey(const Key('send-message')));
      await tester.pumpAndSettle();

      final editable = tester.widget<EditableText>(
        find.descendant(
          of: find.byKey(composerKey),
          matching: find.byType(EditableText),
        ),
      );
      final messageScroll = tester.state<ScrollableState>(
        find
            .descendant(
              of: find.byKey(const Key('message-list')),
              matching: find.byType(Scrollable),
            )
            .first,
      );
      expect(find.text('mensaje nuevo'), findsOneWidget);
      expect(editable.focusNode.hasFocus, isTrue);
      expect(
        messageScroll.position.pixels,
        closeTo(messageScroll.position.minScrollExtent, 0.5),
      );
    },
  );
}

class _ConversationAdapter implements HttpClientAdapter {
  bool _sent = false;

  Map<String, dynamic> _message(int index) => {
    'id': 'm$index',
    'thread_id': 't1',
    'author_type': index == 20 ? 'client' : 'staff',
    'author_id': index == 20 ? testProfile.id : 'staff-1',
    'author_name': index == 20 ? testProfile.name : 'Ana',
    'author_avatar_url': '',
    'body': index == 20 ? 'mensaje nuevo' : 'Mensaje anterior $index',
    'created_at': DateTime(2026, 8, 15, 10, index).toIso8601String(),
    'deleted': false,
    'attachments': <dynamic>[],
  };

  @override
  Future<ResponseBody> fetch(
    RequestOptions options,
    Stream<Uint8List>? requestStream,
    Future<void>? cancelFuture,
  ) async {
    Object payload = <String, dynamic>{};
    if (options.path == '/staff/internal/threads/t1/messages') {
      if (options.method == 'POST') {
        _sent = true;
        payload = _message(20);
      } else {
        payload = [
          for (var index = 0; index < 20; index++) _message(index),
          if (_sent) _message(20),
        ];
      }
    }
    return ResponseBody.fromString(
      jsonEncode(payload),
      200,
      headers: {
        Headers.contentTypeHeader: ['application/json'],
      },
    );
  }

  @override
  void close({bool force = false}) {}
}
