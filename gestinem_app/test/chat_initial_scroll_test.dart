import 'dart:async';

import 'package:dio/dio.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:gestinem/core/api/api_client.dart';
import 'package:gestinem/features/auth/presentation/auth_controller.dart';
import 'package:gestinem/features/messaging/domain/message.dart';
import 'package:gestinem/features/messaging/presentation/conversation_screen.dart';
import 'package:gestinem/features/messaging/presentation/messaging_providers.dart';
import 'package:gestinem/features/messaging/presentation/unified_conversation_screen.dart';

import 'test_helpers.dart';

List<Message> _historial(String id) => List.generate(
  120,
  (index) => Message(
    id: '$id-$index',
    conversationId: id,
    authorType: 'staff',
    authorId: 'staff-1',
    authorName: 'Ana',
    authorAvatarUrl: '',
    body: index == 119
        ? 'Ultimo mensaje de $id'
        : 'Mensaje $index de $id\n${'Texto largo\n' * (index % 8)}',
    createdAt: DateTime(2026, 9, 1).add(Duration(minutes: index)),
    deleted: false,
  ),
);

void _comprobarFinal(WidgetTester tester, String listKey, String id) {
  final scroll = tester.state<ScrollableState>(
    find
        .descendant(
          of: find.byKey(Key(listKey)),
          matching: find.byType(Scrollable),
        )
        .first,
  );
  expect(scroll.position.maxScrollExtent, greaterThan(0));
  expect(scroll.position.pixels, closeTo(scroll.position.minScrollExtent, 0.5));
  expect(find.text('Ultimo mensaje de $id').hitTestable(), findsOneWidget);
}

void main() {
  for (final tipo in ['interno', 'cliente', 'unificado']) {
    testWidgets('$tipo abre al final con carga tardia y alturas variables', (
      tester,
    ) async {
      final carga = Completer<List<Message>>();
      final dio = Dio(BaseOptions(baseUrl: 'https://example.test'))
        ..httpClientAdapter = JsonAdapter(<String, dynamic>{});
      await tester.pumpWidget(
        ProviderScope(
          overrides: [
            sessionProvider.overrideWith((ref) => FakeSessionController(ref)),
            apiClientProvider.overrideWithValue(
              ApiClient(dio: dio, tokenProvider: () => testSession.token),
            ),
            conversationsProvider.overrideWith((ref) async => []),
            internalThreadsProvider.overrideWith((ref) async => []),
            unifiedConversationProvider.overrideWith((ref) async => {}),
            messagesProvider.overrideWith((ref, id) => carga.future),
            internalMessagesProvider.overrideWith((ref, id) => carga.future),
            unifiedMessagesProvider.overrideWith((ref) => carga.future),
          ],
          child: MaterialApp(
            home: Scaffold(
              body: tipo == 'unificado'
                  ? const UnifiedConversationScreen()
                  : ConversationView(
                      conversationId: 't1',
                      internal: tipo == 'interno',
                    ),
            ),
          ),
        ),
      );
      await tester.pump();
      carga.complete(_historial('t1'));
      await tester.pumpAndSettle();

      final listKey = tipo == 'unificado'
          ? 'unified-message-list'
          : 'message-list';
      _comprobarFinal(tester, listKey, 't1');

      // El compositor y sus cambios de altura no deben ocultar el final.
      final composerKey = tipo == 'unificado'
          ? 'unified-message-composer'
          : 'message-composer';
      await tester.enterText(find.byKey(Key(composerKey)), 'Uno\nDos\nTres');
      await tester.pumpAndSettle();
      _comprobarFinal(tester, listKey, 't1');
      await tester.pumpWidget(const SizedBox());
    });
  }

  testWidgets('cambiar y reabrir un chat descarta la posicion del historial', (
    tester,
  ) async {
    final seleccionado = ValueNotifier('t1');
    final dio = Dio(BaseOptions(baseUrl: 'https://example.test'))
      ..httpClientAdapter = JsonAdapter(<String, dynamic>{});
    await tester.pumpWidget(
      ProviderScope(
        overrides: [
          sessionProvider.overrideWith((ref) => FakeSessionController(ref)),
          apiClientProvider.overrideWithValue(
            ApiClient(dio: dio, tokenProvider: () => testSession.token),
          ),
          internalThreadsProvider.overrideWith((ref) async => []),
          internalMessagesProvider.overrideWith(
            (ref, id) async => _historial(id),
          ),
        ],
        child: MaterialApp(
          home: Scaffold(
            body: ValueListenableBuilder<String>(
              valueListenable: seleccionado,
              builder: (_, id, _) =>
                  ConversationView(conversationId: id, internal: true),
            ),
          ),
        ),
      ),
    );
    await tester.pumpAndSettle();
    _comprobarFinal(tester, 'message-list', 't1');
    for (final id in ['t2', 't1']) {
      await tester.drag(
        find.byKey(const Key('message-list')),
        const Offset(0, 1000),
      );
      await tester.pumpAndSettle();
      seleccionado.value = id;
      await tester.pumpAndSettle();
      _comprobarFinal(tester, 'message-list', id);
    }
    await tester.pumpWidget(const SizedBox());
    seleccionado.dispose();
  });
}
