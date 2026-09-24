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
import 'package:gestinem/features/platform/features_provider.dart';
import 'package:gestinem/app/router.dart';
import 'package:gestinem/features/certificates/domain/certificate_request.dart';
import 'package:gestinem/features/certificates/presentation/certificates_providers.dart';
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

class _SesionConCierre extends FakeSessionController {
  _SesionConCierre(super.ref, super.session);

  int cierres = 0;

  @override
  Future<void> logout() async {
    cierres++;
    state = const AsyncData(null);
  }
}

void main() {
  testWidgets('bandeja muestra grupos empleados y clientes en vertical', (
    tester,
  ) async {
    await tester.binding.setSurfaceSize(const Size(1200, 800));
    addTearDown(() => tester.binding.setSurfaceSize(null));
    const profile = UserProfile(
      id: 'staff-1',
      name: 'Empleada',
      email: 'empleada@gestinem.es',
      type: UserType.staff,
      staffRole: StaffRole.empleado,
    );
    const session = AuthSession(token: 'staff-token', profile: profile);
    final threads = [
      for (var index = 0; index < 2; index++)
        InternalThread(
          id: 'thread-$index',
          kind: 'group',
          channel: '',
          title: 'Chat interno largo $index',
          unreadCount: 0,
        ),
    ];

    await tester.pumpWidget(
      ProviderScope(
        overrides: [
          sessionProvider.overrideWith(
            (ref) => FakeSessionController(ref, session),
          ),
          apiClientProvider.overrideWithValue(
            ApiClient(
              dio: Dio(BaseOptions(baseUrl: 'https://example.test')),
              tokenProvider: () => session.token,
            ),
          ),
          conversationsProvider.overrideWith((ref) async => []),
          internalThreadsProvider.overrideWith((ref) async => threads),
          realtimeServiceProvider.overrideWithValue(_FakeRealtime()),
          notificationsServiceProvider.overrideWithValue(_FakeNotifications()),
        ],
        child: const MaterialApp(home: ConversationsScreen()),
      ),
    );
    await tester.pumpAndSettle();

    expect(find.byKey(const Key('inbox-section-groups')), findsOneWidget);
    expect(find.byKey(const Key('inbox-section-employees')), findsOneWidget);
    expect(find.byKey(const Key('inbox-section-clients')), findsOneWidget);
  });

  testWidgets('cliente ve Canal general y Tu asesor sin buscador', (
    tester,
  ) async {
    final channels = [
      Conversation(
        id: 'general',
        companyCode: 'E00006',
        companyName: 'Cliente',
        kind: 'general',
        channelLabel: 'CG',
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

    expect(find.byKey(const Key('client-channel-general')), findsOneWidget);
    expect(find.byKey(const Key('client-channel-private')), findsOneWidget);
    expect(find.text('CG'), findsOneWidget);
    expect(find.text('JJ'), findsOneWidget);
    expect(find.text('3'), findsOneWidget);
    expect(find.byType(TextField), findsOneWidget);
    expect(find.text('Buscar por codigo o nombre'), findsNothing);
    expect(find.byKey(const Key('client-profile-button')), findsNothing);
    expect(find.byKey(const Key('client-documentation-button')), findsNothing);
    expect(find.byIcon(Icons.menu), findsOneWidget);
    expect(tester.widget<AppBar>(find.byType(AppBar)).actions, isNull);
    expect(
      find.byKey(const Key('client-company-profile-button')),
      findsNothing,
    );

    await tester.tap(find.byKey(const Key('client-channel-general')));
    await tester.pumpAndSettle();
    expect(
      find.byKey(const ValueKey('client-conversation-general')),
      findsOneWidget,
    );
    await tester.tap(find.byIcon(Icons.menu));
    await tester.pumpAndSettle();
    expect(find.byKey(const Key('drawer-documentation')), findsOneWidget);
    expect(find.byKey(const Key('drawer-profile')), findsOneWidget);
  });

  testWidgets('cliente abre documentacion desde menu y puede volver', (
    tester,
  ) async {
    await tester.binding.setSurfaceSize(const Size(360, 800));
    addTearDown(() => tester.binding.setSurfaceSize(null));
    late GoRouter router;
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
          platformFeaturesProvider.overrideWith(
            (_) async => const PlatformFeatures(
              documents: true,
              certificates: true,
              invoicing: true,
            ),
          ),
          certificateStatusProvider.overrideWith(
            (_) async =>
                const CertificateStatus(configured: true, status: 'valid'),
          ),
          certificateTypesProvider.overrideWith(
            (_) async => const [
              CertificateType(
                code: 'AEAT_CORRIENTE',
                organization: 'AEAT',
                name: 'Estar al corriente',
              ),
            ],
          ),
          certificateRequestsProvider.overrideWith((_) async => const []),
          conversationsProvider.overrideWith((_) async => []),
          realtimeServiceProvider.overrideWithValue(_FakeRealtime()),
          notificationsServiceProvider.overrideWithValue(_FakeNotifications()),
        ],
        child: Consumer(
          builder: (_, ref, _) {
            router = ref.watch(routerProvider);
            return MaterialApp.router(routerConfig: router);
          },
        ),
      ),
    );
    await tester.pumpAndSettle();
    await tester.tap(find.byIcon(Icons.menu));
    await tester.pumpAndSettle();
    expect(find.byKey(const Key('drawer-certificates')), findsNothing);
    expect(find.text('Mis documentos'), findsNothing);
    expect(find.text('Documentaci\u00f3n'), findsOneWidget);
    expect(find.byKey(const Key('drawer-invoicing')), findsOneWidget);
    final opciones = tester
        .widgetList<ListTile>(
          find.descendant(
            of: find.byType(Drawer),
            matching: find.byType(ListTile),
          ),
        )
        .toList();
    expect(opciones.last.key, const Key('drawer-logout'));
    await tester.tap(find.byKey(const Key('drawer-documentation')));
    await tester.pumpAndSettle();
    expect(find.text('Documentaci\u00f3n'), findsOneWidget);
    expect(router.canPop(), isTrue);
    expect(find.byKey(const Key('drawer-documentation')), findsNothing);

    await tester.tap(find.byKey(const Key('documentation-back')));
    await tester.pumpAndSettle();
    expect(find.byIcon(Icons.menu), findsOneWidget);
    expect(router.canPop(), isFalse);
    await tester.tap(find.byIcon(Icons.menu));
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const Key('drawer-documentation')));
    await tester.pumpAndSettle();
    expect(find.text('Documentaci\u00f3n'), findsOneWidget);
    await tester.tap(find.byKey(const Key('documentation-certificates')));
    await tester.pumpAndSettle();
    expect(find.text('Certificados oficiales'), findsOneWidget);
    expect(find.byKey(const Key('certificate-type-selector')), findsOneWidget);
    await tester.tap(find.byType(BackButton));
    await tester.pumpAndSettle();
    expect(find.text('Documentaci\u00f3n'), findsOneWidget);
    await tester.tap(find.byKey(const Key('documentation-back')));
    await tester.pumpAndSettle();
    expect(find.byIcon(Icons.menu), findsOneWidget);
  });

  for (final perfil in [
    testProfile,
    const UserProfile(
      id: 'staff-1',
      name: 'Gestor',
      email: 'gestor@example.test',
      type: UserType.staff,
      staffRole: StaffRole.admin,
    ),
  ]) {
    testWidgets('ultima opcion cierra sesion de ${perfil.type.name}', (
      tester,
    ) async {
      final sesion = AuthSession(token: 'test-token', profile: perfil);
      late _SesionConCierre controlador;
      await tester.pumpWidget(
        ProviderScope(
          overrides: [
            sessionProvider.overrideWith((ref) {
              controlador = _SesionConCierre(ref, sesion);
              return controlador;
            }),
            apiClientProvider.overrideWithValue(
              ApiClient(
                dio: Dio(BaseOptions(baseUrl: 'https://example.test'))
                  ..httpClientAdapter = JsonAdapter(<String, dynamic>{}),
                tokenProvider: () => sesion.token,
              ),
            ),
            platformFeaturesProvider.overrideWith(
              (_) async => const PlatformFeatures(),
            ),
            conversationsProvider.overrideWith((_) async => []),
            internalThreadsProvider.overrideWith((_) async => []),
            realtimeServiceProvider.overrideWithValue(_FakeRealtime()),
            notificationsServiceProvider.overrideWithValue(
              _FakeNotifications(),
            ),
          ],
          child: Consumer(
            builder: (_, ref, _) =>
                MaterialApp.router(routerConfig: ref.watch(routerProvider)),
          ),
        ),
      );
      await tester.pumpAndSettle();
      await tester.tap(find.byIcon(Icons.menu));
      await tester.pumpAndSettle();
      await tester.scrollUntilVisible(
        find.byKey(const Key('drawer-logout')),
        100,
        scrollable: find.descendant(
          of: find.byType(Drawer),
          matching: find.byType(Scrollable),
        ),
      );
      final opciones = tester
          .widgetList<ListTile>(
            find.descendant(
              of: find.byType(Drawer),
              matching: find.byType(ListTile),
            ),
          )
          .toList();
      expect(opciones.last.key, const Key('drawer-logout'));
      await tester.ensureVisible(find.byKey(const Key('drawer-logout')));
      await tester.tap(find.byKey(const Key('drawer-logout')));
      await tester.pumpAndSettle();
      expect(controlador.cierres, 1);
      expect(controlador.state.valueOrNull, isNull);
      expect(find.byKey(const Key('drawer-logout')), findsNothing);
      expect(find.byKey(const Key('client-login-button')), findsOneWidget);
    });
  }

  testWidgets('staff ve Canal general y Tu asesor por cliente', (
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

    final rows = [
      for (final channel in const [
        ('general', 'CG'),
        ('private', 'Tu asesor'),
      ])
        Conversation(
          id: 'c-${channel.$1}',
          companyCode: 'E00001',
          companyName: 'Empresa Uno',
          kind: channel.$1,
          channelLabel: channel.$2,
          state: 'pendiente',
          unreadCount: channel.$1 == 'general' ? 3 : 0,
          updatedAt: DateTime(2026, 8, 15),
        ),
    ];
    await tester.pumpWidget(
      ProviderScope(
        overrides: [
          sessionProvider.overrideWith(
            (ref) => FakeSessionController(ref, staffSession),
          ),
          conversationsProvider.overrideWith((ref) async => rows),
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
    expect(find.text('Empresa Uno'), findsNWidgets(2));
    expect(find.text('CG'), findsOneWidget);
    expect(find.text('Tu asesor'), findsOneWidget);
    expect(find.byKey(const Key('conversation-c-general')), findsOneWidget);
    expect(find.byKey(const Key('conversation-c-private')), findsOneWidget);
    expect(find.text('3'), findsOneWidget);
    expect(find.text('15/08'), findsNWidgets(2));
  });

  testWidgets('staff abre Nuevo chat y busca clientes invitados', (
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
    final target = Conversation(
      id: 'general-1',
      companyCode: 'E00006',
      companyName: 'Cliente Invitado',
      kind: 'general',
      clientAccessStatus: 'pending',
      state: 'pendiente',
      unreadCount: 0,
      updatedAt: DateTime(2026, 8, 22),
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
          conversationTargetsProvider.overrideWith((ref) async => [target]),
          internalThreadsProvider.overrideWith((ref) async => []),
          realtimeServiceProvider.overrideWithValue(_FakeRealtime()),
          notificationsServiceProvider.overrideWithValue(_FakeNotifications()),
        ],
        child: const MaterialApp(home: ConversationsScreen()),
      ),
    );
    await tester.pumpAndSettle();

    await tester.tap(find.byKey(const Key('new-chat-button')));
    await tester.pumpAndSettle();
    expect(find.text('Nuevo chat'), findsOneWidget);
    expect(find.text('Cliente Invitado'), findsOneWidget);
    expect(find.byKey(const Key('new-chat-search')), findsOneWidget);

    await tester.enterText(
      find.byKey(const Key('new-chat-search')),
      'cliente que no existe',
    );
    await tester.pump();
    expect(find.text('No hay clientes invitados disponibles'), findsOneWidget);
  });

  testWidgets('Nuevo chat abre el Canal general por defecto', (tester) async {
    await tester.binding.setSurfaceSize(const Size(1200, 800));
    addTearDown(() => tester.binding.setSurfaceSize(null));
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
    final targets = [
      for (final kind in ['general', 'private'])
        Conversation(
          id: kind,
          companyCode: 'E00006',
          companyName: 'Cliente Invitado',
          kind: kind,
          clientAccessStatus: 'pending',
          state: 'pendiente',
          unreadCount: 0,
          updatedAt: DateTime(2026, 8, 22),
        ),
    ];
    final adapter = JsonAdapter({
      'id': 'general',
      'company_code': 'E00006',
      'company_name': 'Cliente Invitado',
      'kind': 'general',
      'client_access_status': 'pending',
      'state': 'pendiente',
      'unread_count': 0,
      'updated_at': '2026-08-22T10:00:00Z',
      'started_at': '2026-08-22T10:00:00Z',
      'last_message': null,
    });
    final api = ApiClient(
      dio: Dio(BaseOptions(baseUrl: 'https://example.test'))
        ..httpClientAdapter = adapter,
      tokenProvider: () => staffSession.token,
    );

    await tester.pumpWidget(
      ProviderScope(
        overrides: [
          sessionProvider.overrideWith(
            (ref) => FakeSessionController(ref, staffSession),
          ),
          apiClientProvider.overrideWithValue(api),
          conversationsProvider.overrideWith((ref) async => []),
          conversationTargetsProvider.overrideWith((ref) async => targets),
          messagesProvider.overrideWith((ref, id) async => []),
          internalThreadsProvider.overrideWith((ref) async => []),
          realtimeServiceProvider.overrideWithValue(_FakeRealtime()),
          notificationsServiceProvider.overrideWithValue(_FakeNotifications()),
        ],
        child: const MaterialApp(home: ConversationsScreen()),
      ),
    );
    await tester.pumpAndSettle();

    await tester.tap(find.byKey(const Key('new-chat-button')));
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const Key('new-chat-group-E00006')));
    await tester.pumpAndSettle();

    expect(adapter.lastRequest!.path, '/staff/conversations/general/start');
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

  testWidgets('empleado ve Canal general, sus grupos y administrador', (
    tester,
  ) async {
    const employeeProfile = UserProfile(
      id: 'employee-1',
      name: 'Analia',
      email: 'analia@gestinem.es',
      type: UserType.staff,
      staffRole: StaffRole.empleado,
      channels: [],
    );
    const employeeSession = AuthSession(
      token: 'employee-token',
      profile: employeeProfile,
    );
    final conversations = [
      Conversation(
        id: 'general-1',
        companyCode: 'E00001',
        companyName: 'Cliente General',
        kind: 'general',
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
        counterpartId: 'admin-1',
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

    expect(find.text('CG'), findsWidgets);
    expect(find.text('LA'), findsNothing);
    expect(find.text('Todos'), findsNothing);
    expect(find.text('Equipo nóminas'), findsOneWidget);
    expect(find.text('Grupos'), findsOneWidget);
    expect(find.text('Empleados'), findsOneWidget);
    expect(find.text('Clientes'), findsOneWidget);
    expect(find.byKey(const Key('internal-thread-group-1')), findsOneWidget);
    expect(find.byKey(const Key('internal-thread-direct-1')), findsOneWidget);
    expect(find.text('Juan José'), findsOneWidget);
    expect(find.text('Analia'), findsOneWidget);
    expect(find.text('Cliente General'), findsOneWidget);

    await tester.tap(find.byIcon(Icons.menu));
    await tester.pumpAndSettle();
    expect(find.text('Gestionar grupos internos'), findsNothing);
  });

  testWidgets('usuario actual no aparece en la seccion Empleados', (
    tester,
  ) async {
    const adminProfile = UserProfile(
      id: 'admin-1',
      name: 'Juan José Domínguez',
      email: 'juanjose@gestinem.es',
      type: UserType.staff,
      staffRole: StaffRole.admin,
    );
    const adminSession = AuthSession(
      token: 'admin-token',
      profile: adminProfile,
    );
    const threads = [
      InternalThread(
        id: 'direct-self',
        kind: 'direct',
        channel: '',
        title: 'Juan José Domínguez',
        unreadCount: 0,
        counterpartId: 'admin-1',
      ),
      InternalThread(
        id: 'direct-other',
        kind: 'direct',
        channel: '',
        title: 'Analia',
        unreadCount: 0,
        counterpartId: 'employee-2',
      ),
      InternalThread(
        id: 'direct-admin2',
        kind: 'direct',
        channel: '',
        title: 'Roberto',
        unreadCount: 0,
        counterpartId: 'admin-3',
      ),
      InternalThread(
        id: 'direct-inactive',
        kind: 'direct',
        channel: '',
        title: 'Empleado inactivo',
        unreadCount: 0,
        counterpartId: 'employee-4',
        counterpartActive: false,
      ),
    ];

    await tester.pumpWidget(
      ProviderScope(
        overrides: [
          sessionProvider.overrideWith(
            (ref) => FakeSessionController(ref, adminSession),
          ),
          apiClientProvider.overrideWithValue(
            ApiClient(
              dio: Dio(BaseOptions(baseUrl: 'https://example.test')),
              tokenProvider: () => adminSession.token,
            ),
          ),
          conversationsProvider.overrideWith((ref) async => []),
          internalThreadsProvider.overrideWith((ref) async => threads),
          realtimeServiceProvider.overrideWithValue(_FakeRealtime()),
          notificationsServiceProvider.overrideWithValue(_FakeNotifications()),
        ],
        child: const MaterialApp(home: ConversationsScreen()),
      ),
    );
    await tester.pumpAndSettle();

    // El thread consigo mismo no debe aparecer
    expect(find.byKey(const Key('internal-thread-direct-self')), findsNothing);
    // Otros empleados sí aparecen
    expect(
      find.byKey(const Key('internal-thread-direct-other')),
      findsOneWidget,
    );
    expect(find.text('Analia'), findsOneWidget);
    // Otro administrador también aparece
    expect(
      find.byKey(const Key('internal-thread-direct-admin2')),
      findsOneWidget,
    );
    expect(find.text('Roberto'), findsOneWidget);
    expect(
      find.byKey(const Key('internal-thread-direct-inactive')),
      findsNothing,
    );
  });

  testWidgets('exclusion del usuario actual es case-insensitive', (
    tester,
  ) async {
    const adminProfile = UserProfile(
      id: 'AbC-123-DeF',
      name: 'Admin',
      email: 'admin@gestinem.es',
      type: UserType.staff,
      staffRole: StaffRole.admin,
    );
    const adminSession = AuthSession(
      token: 'admin-token',
      profile: adminProfile,
    );
    const threads = [
      InternalThread(
        id: 'direct-self-case',
        kind: 'direct',
        channel: '',
        title: 'Admin',
        unreadCount: 0,
        counterpartId: 'abc-123-def',
      ),
      InternalThread(
        id: 'direct-other-case',
        kind: 'direct',
        channel: '',
        title: 'Empleada',
        unreadCount: 0,
        counterpartId: 'other-id',
      ),
    ];

    await tester.pumpWidget(
      ProviderScope(
        overrides: [
          sessionProvider.overrideWith(
            (ref) => FakeSessionController(ref, adminSession),
          ),
          apiClientProvider.overrideWithValue(
            ApiClient(
              dio: Dio(BaseOptions(baseUrl: 'https://example.test')),
              tokenProvider: () => adminSession.token,
            ),
          ),
          conversationsProvider.overrideWith((ref) async => []),
          internalThreadsProvider.overrideWith((ref) async => threads),
          realtimeServiceProvider.overrideWithValue(_FakeRealtime()),
          notificationsServiceProvider.overrideWithValue(_FakeNotifications()),
        ],
        child: const MaterialApp(home: ConversationsScreen()),
      ),
    );
    await tester.pumpAndSettle();

    expect(
      find.byKey(const Key('internal-thread-direct-self-case')),
      findsNothing,
    );
    expect(
      find.byKey(const Key('internal-thread-direct-other-case')),
      findsOneWidget,
    );
  });
}
