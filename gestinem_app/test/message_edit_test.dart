import 'package:dio/dio.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:gestinem/core/api/api_client.dart';
import 'package:gestinem/features/auth/domain/user_profile.dart';
import 'package:gestinem/features/auth/presentation/auth_controller.dart';
import 'package:gestinem/features/messaging/data/messaging_repository.dart';
import 'package:gestinem/features/messaging/domain/message.dart';
import 'package:gestinem/features/messaging/presentation/conversation_screen.dart';
import 'package:gestinem/features/messaging/presentation/message_bubble.dart';
import 'package:gestinem/features/messaging/presentation/message_edit_dialogs.dart';
import 'package:gestinem/features/messaging/presentation/messaging_providers.dart';
import 'package:gestinem/features/messaging/presentation/unified_conversation_screen.dart';

import 'test_helpers.dart';

Map<String, dynamic> mensajeJson() => {
  'id': 'm1',
  'conversation_id': 'c1',
  'author_type': 'client',
  'author_id': testProfile.id,
  'body': 'Original',
  'created_at': '2026-09-18T10:00:00Z',
  'edited_at': '2026-09-18T11:00:00Z',
  'can_view_history': true,
};

void main() {
  testWidgets(
    'historial muestra todas las versiones con fechas sin repetir consultas',
    (tester) async {
      var consultas = 0;
      await tester.pumpWidget(
        MaterialApp(
          home: Builder(
            builder: (context) => Scaffold(
              body: TextButton(
                onPressed: () => verHistorialMensaje(context, () async {
                  consultas++;
                  return [
                    MessageVersion(
                      body: 'Primer texto',
                      createdAt: DateTime(2026, 9, 18, 10),
                      replacedAt: DateTime(2026, 9, 18, 11),
                    ),
                    MessageVersion(
                      body: 'Segundo texto',
                      createdAt: DateTime(2026, 9, 18, 11),
                      replacedAt: DateTime(2026, 9, 18, 12),
                    ),
                  ];
                }),
                child: const Text('Abrir'),
              ),
            ),
          ),
        ),
      );
      await tester.tap(find.text('Abrir'));
      await tester.pumpAndSettle();
      expect(find.text('Original'), findsOneWidget);
      expect(find.text('Version 2'), findsOneWidget);
      expect(find.text('Primer texto'), findsOneWidget);
      expect(find.text('Segundo texto'), findsOneWidget);
      expect(find.textContaining('18/09/2026 10:00:00'), findsOneWidget);
      expect(consultas, 1);
      await tester.tap(find.text('Cerrar'));
      await tester.pumpAndSettle();
    },
  );

  test('interpreta la marca y permiso; por defecto deniega historial', () {
    final mensaje = Message.fromJson(mensajeJson());
    expect(mensaje.editedAt, isNotNull);
    expect(mensaje.canViewHistory, isTrue);
    expect(
      Message.fromJson(
        mensajeJson()..remove('can_view_history'),
      ).canViewHistory,
      isFalse,
    );
  });

  testWidgets('marca editado incluso con estados de lectura ocultos', (
    tester,
  ) async {
    await tester.pumpWidget(
      MaterialApp(
        home: Scaffold(
          body: MessageBubble(
            message: Message.fromJson(mensajeJson()),
            mine: false,
            mostrarEstados: false,
          ),
        ),
      ),
    );
    expect(find.textContaining('Editado'), findsOneWidget);
    expect(find.text('Original'), findsOneWidget);
  });

  for (final internal in [false, true]) {
    test(
      'edicion envia original y usa ruta ${internal ? 'interna' : 'cliente'}',
      () async {
        final adapter = JsonAdapter(mensajeJson());
        final dio = Dio(BaseOptions(baseUrl: 'https://example.test'))
          ..httpClientAdapter = adapter;
        final repository = MessagingRepository(
          ApiClient(dio: dio, tokenProvider: () => 'test'),
        );
        await repository.edit(
          testProfile,
          Message.fromJson(mensajeJson()),
          'Nuevo',
          internal: internal,
        );
        expect(adapter.lastRequest!.method, 'PATCH');
        expect(
          adapter.lastRequest!.path,
          internal ? '/staff/internal/messages/m1' : '/client/messages/m1',
        );
        expect(adapter.lastRequest!.data, {
          'body': 'Nuevo',
          'original_body': 'Original',
        });
      },
    );
  }

  for (final modo in ['normal', 'interno', 'unificado']) {
    testWidgets('ofrece editar propio y guarda desde chat $modo', (
      tester,
    ) async {
      final interno = modo == 'interno';
      final perfil = interno
          ? const UserProfile(
              id: 'staff-1',
              name: 'Ana',
              email: 'ana@gestinem.es',
              type: UserType.staff,
            )
          : testProfile;
      final session = AuthSession(token: 'test', profile: perfil);
      final json = mensajeJson()
        ..['author_id'] = perfil.id
        ..['author_type'] = perfil.type.name
        ..['can_view_history'] = false;
      final mensaje = Message.fromJson(json);
      final adapter = JsonAdapter(json);
      final dio = Dio(BaseOptions(baseUrl: 'https://example.test'))
        ..httpClientAdapter = adapter;
      await tester.pumpWidget(
        ProviderScope(
          overrides: [
            sessionProvider.overrideWith(
              (ref) => FakeSessionController(ref, session),
            ),
            apiClientProvider.overrideWithValue(
              ApiClient(dio: dio, tokenProvider: () => 'test'),
            ),
            messagesProvider.overrideWith((ref, id) async => [mensaje]),
            internalMessagesProvider.overrideWith((ref, id) async => [mensaje]),
            unifiedMessagesProvider.overrideWith((ref) async => [mensaje]),
            unifiedConversationProvider.overrideWith((ref) async => {}),
            conversationsProvider.overrideWith((ref) async => []),
            internalThreadsProvider.overrideWith((ref) async => []),
          ],
          child: MaterialApp(
            home: modo == 'unificado'
                ? const UnifiedConversationScreen()
                : Scaffold(
                    body: ConversationView(
                      conversationId: 'c1',
                      internal: interno,
                    ),
                  ),
          ),
        ),
      );
      await tester.pumpAndSettle();
      await tester.tap(find.text('Original'));
      await tester.pumpAndSettle();
      expect(find.byKey(const Key('message-history-option')), findsNothing);
      await tester.tap(find.byKey(const Key('edit-message-option')));
      await tester.pumpAndSettle();
      await tester.enterText(
        find.byKey(const Key('edit-message-body')),
        'Nuevo texto',
      );
      await tester.tap(find.text('Guardar'));
      await tester.pumpAndSettle();
      expect(find.byKey(const Key('edit-message-body')), findsNothing);
      await tester.pumpWidget(const SizedBox());
    });
  }

  testWidgets(
    'solo muestra historial si el servidor concede permiso; no edita ajenos',
    (tester) async {
      for (final permitido in [false, true]) {
        final mensaje = Message.fromJson(
          mensajeJson()
            ..['author_id'] = 'otro'
            ..['can_view_history'] = permitido,
        );
        final dio = Dio(BaseOptions(baseUrl: 'https://example.test'))
          ..httpClientAdapter = JsonAdapter({});
        await tester.pumpWidget(
          ProviderScope(
            overrides: [
              sessionProvider.overrideWith((ref) => FakeSessionController(ref)),
              apiClientProvider.overrideWithValue(
                ApiClient(dio: dio, tokenProvider: () => 'test'),
              ),
              messagesProvider.overrideWith((ref, id) async => [mensaje]),
              conversationsProvider.overrideWith((ref) async => []),
            ],
            child: const MaterialApp(
              home: Scaffold(body: ConversationView(conversationId: 'c1')),
            ),
          ),
        );
        await tester.pumpAndSettle();
        await tester.tap(find.text('Original'));
        await tester.pumpAndSettle();
        expect(find.byKey(const Key('edit-message-option')), findsNothing);
        expect(
          find.byKey(const Key('message-history-option')),
          permitido ? findsOneWidget : findsNothing,
        );
        await tester.pumpWidget(const SizedBox());
      }
    },
  );

  testWidgets('dialogo rechaza vacio y mantiene texto si falla guardado', (
    tester,
  ) async {
    var intentos = 0;
    await tester.pumpWidget(
      MaterialApp(
        home: Builder(
          builder: (context) => Scaffold(
            body: TextButton(
              onPressed: () => editarMensaje(
                context,
                Message.fromJson(mensajeJson()),
                (texto) async {
                  intentos++;
                  throw Exception('Sin conexion');
                },
              ),
              child: const Text('Abrir'),
            ),
          ),
        ),
      ),
    );
    await tester.tap(find.text('Abrir'));
    await tester.pumpAndSettle();
    await tester.enterText(find.byKey(const Key('edit-message-body')), '   ');
    await tester.tap(find.text('Guardar'));
    await tester.pumpAndSettle();
    expect(intentos, 0);
    expect(find.text('El mensaje no puede estar vacio'), findsOneWidget);
    await tester.enterText(find.byKey(const Key('edit-message-body')), 'Nuevo');
    await tester.tap(find.text('Guardar'));
    await tester.pumpAndSettle();
    expect(intentos, 1);
    expect(find.byKey(const Key('edit-message-body')), findsOneWidget);
    expect(find.text('Nuevo'), findsOneWidget);
    await tester.tap(find.text('Cancelar'));
    await tester.pumpAndSettle();
  });
}
