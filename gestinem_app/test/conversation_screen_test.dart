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
      id: 'm-other', conversationId: 't1', authorType: 'client',
      authorId: 'client-2', authorName: 'Otra persona', authorAvatarUrl: '',
      body: 'Mensaje ajeno', createdAt: DateTime(2026, 8, 15), deleted: false,
    );
    final own = Message(
      id: 'm-own', conversationId: 't1', authorType: 'client',
      authorId: testProfile.id, authorName: testProfile.name, authorAvatarUrl: '',
      body: 'Mensaje propio', createdAt: DateTime(2026, 8, 15), deleted: false,
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
          internalMessagesProvider.overrideWith((ref, id) async => [message]),
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
    expect(find.byKey(const Key('message-composer')), findsOneWidget);
    expect(find.byKey(const Key('send-message')), findsOneWidget);
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
}
