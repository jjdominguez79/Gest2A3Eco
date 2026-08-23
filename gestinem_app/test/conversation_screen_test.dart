import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:go_router/go_router.dart';
import 'package:gestinem/features/auth/presentation/auth_controller.dart';
import 'package:gestinem/features/messaging/domain/conversation.dart';
import 'package:gestinem/features/messaging/domain/message.dart';
import 'package:gestinem/features/messaging/presentation/conversation_screen.dart';
import 'package:gestinem/features/messaging/presentation/messaging_providers.dart';

import 'test_helpers.dart';

void main() {
  testWidgets('conversacion renderiza historial y compositor', (tester) async {
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
  });

  testWidgets('volver desde un chat interno abre la lista de inicio', (
    tester,
  ) async {
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
