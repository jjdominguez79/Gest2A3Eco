import 'package:flutter/material.dart';
import 'package:dio/dio.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:gestinem/features/auth/presentation/auth_controller.dart';
import 'package:gestinem/features/messaging/domain/conversation.dart';
import 'package:gestinem/features/messaging/presentation/conversations_screen.dart';
import 'package:gestinem/features/messaging/presentation/messaging_providers.dart';
import 'package:gestinem/core/api/api_client.dart';
import 'package:gestinem/core/notifications/notifications_service.dart';
import 'package:gestinem/core/websocket/realtime_service.dart';
import 'package:gestinem/features/auth/domain/user_profile.dart';
import 'package:go_router/go_router.dart';

import 'test_helpers.dart';

class _FakeRealtime extends RealtimeService {
  @override
  Future<void> connect(AuthSession session, ApiClient api) async {}
}

class _FakeNotifications extends NotificationsService {
  @override
  Future<void> initialize(AuthSession session, ApiClient api) async {}
}

void main() {
  testWidgets('cliente ve canales separados sin buscador ni menu', (
    tester,
  ) async {
    final channels = [
      Conversation(
        id: 'laboral',
        companyCode: 'E00006',
        companyName: 'Cliente',
        kind: 'laboral',
        channelLabel: 'LA',
        state: 'pendiente',
        unreadCount: 0,
        updatedAt: DateTime(2026, 8, 18),
      ),
      Conversation(
        id: 'fiscal',
        companyCode: 'E00006',
        companyName: 'Cliente',
        kind: 'fiscal',
        channelLabel: 'CF',
        state: 'pendiente',
        unreadCount: 3,
        updatedAt: DateTime(2026, 8, 18),
      ),
      Conversation(
        id: 'private',
        companyCode: 'E00006',
        companyName: 'Cliente',
        kind: 'private',
        channelLabel: 'JJ',
        state: 'pendiente',
        unreadCount: 0,
        updatedAt: DateTime(2026, 8, 18),
      ),
    ];
    await tester.pumpWidget(
      ProviderScope(
        overrides: [
          sessionProvider.overrideWith((ref) => FakeSessionController(ref)),
          apiClientProvider.overrideWithValue(
            ApiClient(
              dio: Dio(BaseOptions(baseUrl: 'https://example.test'))
                ..httpClientAdapter = JsonAdapter(<String, dynamic>{}),
              tokenProvider: () => testSession.token,
            ),
          ),
          conversationsProvider.overrideWith((ref) async => channels),
          messagesProvider.overrideWith((ref, id) async => []),
          realtimeServiceProvider.overrideWithValue(_FakeRealtime()),
          notificationsServiceProvider.overrideWithValue(_FakeNotifications()),
        ],
        child: const MaterialApp(home: ConversationsScreen()),
      ),
    );
    await tester.pumpAndSettle();

    expect(find.byKey(const Key('client-channel-laboral')), findsOneWidget);
    expect(find.byKey(const Key('client-channel-fiscal')), findsOneWidget);
    expect(find.byKey(const Key('client-channel-private')), findsOneWidget);
    expect(find.text('LA'), findsOneWidget);
    expect(find.text('CF'), findsOneWidget);
    expect(find.text('JJ'), findsOneWidget);
    expect(find.text('3'), findsOneWidget);
    expect(find.byType(TextField), findsOneWidget);
    expect(find.text('Buscar por codigo o nombre'), findsNothing);
    expect(find.byKey(const Key('client-profile-button')), findsOneWidget);

    await tester.tap(find.byKey(const Key('client-channel-fiscal')));
    await tester.pumpAndSettle();
    expect(
      find.byKey(const ValueKey('client-conversation-fiscal')),
      findsOneWidget,
    );
  });

  testWidgets('staff ve lista agrupada por cliente', (tester) async {
    const staffProfile = UserProfile(
      id: 'staff-1',
      name: 'Gestor',
      email: 'gestor@gestinem.es',
      type: UserType.staff,
      staffRole: StaffRole.admin,
    );
    const staffSession = AuthSession(
      token: 'staff-token',
      profile: staffProfile,
    );

    final row = Conversation(
      id: 'c1',
      companyCode: 'E00001',
      companyName: 'Empresa Uno',
      kind: 'fiscal',
      state: 'pendiente',
      unreadCount: 3,
      updatedAt: DateTime(2026, 8, 15),
    );
    await tester.pumpWidget(
      ProviderScope(
        overrides: [
          sessionProvider.overrideWith(
            (ref) => FakeSessionController(ref, staffSession),
          ),
          conversationsProvider.overrideWith((ref) async => [row]),
          internalThreadsProvider.overrideWith((ref) async => []),
          realtimeServiceProvider.overrideWithValue(_FakeRealtime()),
          notificationsServiceProvider.overrideWithValue(_FakeNotifications()),
        ],
        child: const MaterialApp(home: ConversationsScreen()),
      ),
    );
    await tester.pump();
    await tester.pump();

    expect(find.byKey(const Key('conversation-list')), findsOneWidget);
    expect(find.text('Gestor'), findsOneWidget);
    expect(find.text('Empresa Uno'), findsOneWidget);
    expect(find.textContaining('E00001'), findsOneWidget);
    expect(find.text('3'), findsOneWidget);
  });

  testWidgets('Conversaciones cierra el menu aunque ya sea la ruta activa', (
    tester,
  ) async {
    const staffProfile = UserProfile(
      id: 'staff-1',
      name: 'Gestor',
      email: 'gestor@gestinem.es',
      type: UserType.staff,
      staffRole: StaffRole.admin,
    );
    const staffSession = AuthSession(
      token: 'staff-token',
      profile: staffProfile,
    );
    final router = GoRouter(
      routes: [
        GoRoute(path: '/', builder: (_, _) => const ConversationsScreen()),
      ],
    );

    await tester.pumpWidget(
      ProviderScope(
        overrides: [
          sessionProvider.overrideWith(
            (ref) => FakeSessionController(ref, staffSession),
          ),
          apiClientProvider.overrideWithValue(
            ApiClient(
              dio: Dio(BaseOptions(baseUrl: 'https://example.test')),
              tokenProvider: () => staffSession.token,
            ),
          ),
          conversationsProvider.overrideWith((ref) async => []),
          internalThreadsProvider.overrideWith((ref) async => []),
          realtimeServiceProvider.overrideWithValue(_FakeRealtime()),
          notificationsServiceProvider.overrideWithValue(_FakeNotifications()),
        ],
        child: MaterialApp.router(routerConfig: router),
      ),
    );
    await tester.pumpAndSettle();

    await tester.tap(find.byIcon(Icons.menu));
    await tester.pumpAndSettle();
    expect(find.byKey(const Key('drawer-conversations')), findsOneWidget);

    await tester.tap(find.byKey(const Key('drawer-conversations')));
    await tester.pumpAndSettle();
    expect(find.byKey(const Key('drawer-conversations')), findsNothing);
  });

  testWidgets('empleado solo ve canales autorizados grupos y administrador', (
    tester,
  ) async {
    const employeeProfile = UserProfile(
      id: 'employee-1',
      name: 'Analia',
      email: 'analia@gestinem.es',
      type: UserType.staff,
      staffRole: StaffRole.empleado,
      channels: ['fiscal'],
    );
    const employeeSession = AuthSession(
      token: 'employee-token',
      profile: employeeProfile,
    );
    final conversations = [
      Conversation(
        id: 'fiscal-1',
        companyCode: 'E00001',
        companyName: 'Cliente Fiscal',
        kind: 'fiscal',
        state: 'pendiente',
        unreadCount: 0,
        updatedAt: DateTime(2026, 8, 19),
      ),
    ];
    const threads = [
      InternalThread(
        id: 'group-1',
        kind: 'group',
        channel: '',
        title: 'Equipo nóminas',
        unreadCount: 0,
      ),
      InternalThread(
        id: 'direct-1',
        kind: 'direct',
        channel: '',
        title: 'Juan José',
        unreadCount: 0,
      ),
    ];

    await tester.pumpWidget(
      ProviderScope(
        overrides: [
          sessionProvider.overrideWith(
            (ref) => FakeSessionController(ref, employeeSession),
          ),
          apiClientProvider.overrideWithValue(
            ApiClient(
              dio: Dio(BaseOptions(baseUrl: 'https://example.test')),
              tokenProvider: () => employeeSession.token,
            ),
          ),
          conversationsProvider.overrideWith((ref) async => conversations),
          internalThreadsProvider.overrideWith((ref) async => threads),
          realtimeServiceProvider.overrideWithValue(_FakeRealtime()),
          notificationsServiceProvider.overrideWithValue(_FakeNotifications()),
        ],
        child: const MaterialApp(home: ConversationsScreen()),
      ),
    );
    await tester.pumpAndSettle();

    expect(find.text('CF'), findsWidgets);
    expect(find.text('LA'), findsNothing);
    expect(find.text('Todos'), findsNothing);
    expect(find.text('Equipo nóminas'), findsOneWidget);
    expect(find.text('Administrador'), findsOneWidget);
    expect(find.text('Analia'), findsOneWidget);
    expect(find.text('Cliente Fiscal'), findsOneWidget);
  });
}
