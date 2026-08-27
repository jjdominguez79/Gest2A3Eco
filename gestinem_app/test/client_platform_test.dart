import 'package:dio/dio.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:gestinem/core/api/api_client.dart';
import 'package:gestinem/core/notifications/notifications_service.dart';
import 'package:gestinem/core/websocket/realtime_service.dart';
import 'package:gestinem/features/auth/domain/user_profile.dart';
import 'package:gestinem/features/auth/presentation/auth_controller.dart';
import 'package:gestinem/features/company_profile/domain/company_profile.dart';
import 'package:gestinem/features/company_profile/presentation/company_profile_providers.dart';
import 'package:gestinem/features/company_profile/presentation/company_profile_screen.dart';
import 'package:gestinem/features/invoicing/presentation/invoicing_providers.dart';
import 'package:gestinem/features/messaging/presentation/conversations_screen.dart';
import 'package:gestinem/features/messaging/presentation/messaging_providers.dart';
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
  // -- Perfil empresarial --
  group('CompanyProfileScreen', () {
    testWidgets('renderiza campos del perfil', (tester) async {
      const profile = CompanyProfile(
        companyCode: 'E00001',
        name: 'Test Corp',
        legalName: 'Test Corporation SL',
        taxId: 'B12345678',
        address: 'Calle Mayor 1',
        postalCode: '28001',
        city: 'Madrid',
        province: 'Madrid',
        country: 'ES',
        phone: '600000000',
        email: 'info@testcorp.es',
      );

      await tester.pumpWidget(
        ProviderScope(
          overrides: [
            sessionProvider.overrideWith(
              (ref) => FakeSessionController(ref),
            ),
            companyProfileProvider.overrideWith(
              (ref) async => profile,
            ),
          ],
          child: const MaterialApp(home: CompanyProfileScreen()),
        ),
      );
      await tester.pumpAndSettle();

      expect(find.text('Mi empresa'), findsOneWidget);
      expect(find.text('Test Corporation SL'), findsOneWidget);
      expect(find.text('B12345678'), findsOneWidget);
      expect(find.text('Calle Mayor 1'), findsOneWidget);
      expect(find.text('28001'), findsOneWidget);
      expect(find.text('Madrid'), findsNWidgets(2));
      expect(find.text('600000000'), findsOneWidget);
      expect(find.text('info@testcorp.es'), findsOneWidget);
    });

    testWidgets('solo lectura - no hay campos editables', (tester) async {
      const profile = CompanyProfile(
        companyCode: 'E00001',
        name: 'Test Corp',
        legalName: 'Test Corporation SL',
        taxId: 'B12345678',
      );

      await tester.pumpWidget(
        ProviderScope(
          overrides: [
            sessionProvider.overrideWith(
              (ref) => FakeSessionController(ref),
            ),
            companyProfileProvider.overrideWith(
              (ref) async => profile,
            ),
          ],
          child: const MaterialApp(home: CompanyProfileScreen()),
        ),
      );
      await tester.pumpAndSettle();

      expect(find.byType(TextFormField), findsNothing);
      expect(find.byType(TextField), findsNothing);
      expect(find.byType(ElevatedButton), findsNothing);
    });

    testWidgets('campos opcionales vacios no se muestran', (tester) async {
      const profile = CompanyProfile(
        companyCode: 'E00002',
        name: 'Minimal Corp',
      );

      await tester.pumpWidget(
        ProviderScope(
          overrides: [
            sessionProvider.overrideWith(
              (ref) => FakeSessionController(ref),
            ),
            companyProfileProvider.overrideWith(
              (ref) async => profile,
            ),
          ],
          child: const MaterialApp(home: CompanyProfileScreen()),
        ),
      );
      await tester.pumpAndSettle();

      expect(find.text('Minimal Corp'), findsOneWidget);
      expect(find.text('NIF/CIF'), findsNothing);
      expect(find.text('Telefono'), findsNothing);
      expect(find.text('Correo'), findsNothing);
    });

    testWidgets('muestra error de carga', (tester) async {
      await tester.pumpWidget(
        ProviderScope(
          overrides: [
            sessionProvider.overrideWith(
              (ref) => FakeSessionController(ref),
            ),
            companyProfileProvider.overrideWith(
              (ref) => throw Exception('Network error'),
            ),
          ],
          child: const MaterialApp(home: CompanyProfileScreen()),
        ),
      );
      await tester.pumpAndSettle();

      expect(find.textContaining('Error'), findsOneWidget);
    });
  });

  // -- Pantalla cliente: boton facturacion condicionado --
  group('Client screen - invoicing button', () {
    testWidgets('muestra boton facturacion cuando config enabled', (
      tester,
    ) async {
      await tester.pumpWidget(
        ProviderScope(
          overrides: [
            sessionProvider.overrideWith(
              (ref) => FakeSessionController(ref),
            ),
            apiClientProvider.overrideWithValue(
              ApiClient(
                dio: Dio(BaseOptions(baseUrl: 'https://example.test'))
                  ..httpClientAdapter = JsonAdapter({}),
                tokenProvider: () => testSession.token,
              ),
            ),
            invoicingConfigProvider.overrideWith(
              (ref) async => {'enabled': true},
            ),
            conversationsProvider.overrideWith((ref) async => []),
            realtimeServiceProvider.overrideWithValue(_FakeRealtime()),
            notificationsServiceProvider.overrideWithValue(
              _FakeNotifications(),
            ),
          ],
          child: const MaterialApp(home: ConversationsScreen()),
        ),
      );
      await tester.pumpAndSettle();

      expect(
        find.byKey(const Key('client-invoicing-button')),
        findsOneWidget,
      );
    });

    testWidgets('oculta boton facturacion cuando config disabled', (
      tester,
    ) async {
      await tester.pumpWidget(
        ProviderScope(
          overrides: [
            sessionProvider.overrideWith(
              (ref) => FakeSessionController(ref),
            ),
            apiClientProvider.overrideWithValue(
              ApiClient(
                dio: Dio(BaseOptions(baseUrl: 'https://example.test'))
                  ..httpClientAdapter = JsonAdapter({}),
                tokenProvider: () => testSession.token,
              ),
            ),
            invoicingConfigProvider.overrideWith(
              (ref) async => {'enabled': false},
            ),
            conversationsProvider.overrideWith((ref) async => []),
            realtimeServiceProvider.overrideWithValue(_FakeRealtime()),
            notificationsServiceProvider.overrideWithValue(
              _FakeNotifications(),
            ),
          ],
          child: const MaterialApp(home: ConversationsScreen()),
        ),
      );
      await tester.pumpAndSettle();

      expect(
        find.byKey(const Key('client-invoicing-button')),
        findsNothing,
      );
    });
  });

  // -- Drawer staff admin --
  group('Staff drawer', () {
    testWidgets('staff admin ve opciones admin y no ve opciones cliente', (
      tester,
    ) async {
      const staffProfile = UserProfile(
        id: 'staff-1',
        name: 'Admin',
        email: 'admin@gestinem.es',
        type: UserType.staff,
        staffRole: StaffRole.admin,
      );
      const staffSession = AuthSession(
        token: 'staff-token',
        profile: staffProfile,
      );

      final router = GoRouter(
        routes: [
          GoRoute(
            path: '/',
            builder: (_, _) => const ConversationsScreen(),
          ),
          GoRoute(
            path: '/groups',
            builder: (_, _) => const Scaffold(),
          ),
          GoRoute(
            path: '/campaigns',
            builder: (_, _) => const Scaffold(),
          ),
          GoRoute(
            path: '/employees',
            builder: (_, _) => const Scaffold(),
          ),
          GoRoute(
            path: '/clients',
            builder: (_, _) => const Scaffold(),
          ),
          GoRoute(
            path: '/profile',
            builder: (_, _) => const Scaffold(),
          ),
          GoRoute(
            path: '/about',
            builder: (_, _) => const Scaffold(),
          ),
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
            notificationsServiceProvider.overrideWithValue(
              _FakeNotifications(),
            ),
          ],
          child: MaterialApp.router(routerConfig: router),
        ),
      );
      await tester.pumpAndSettle();

      await tester.tap(find.byIcon(Icons.menu));
      await tester.pumpAndSettle();

      expect(find.text('Gestionar grupos internos'), findsOneWidget);
      expect(find.byKey(const Key('drawer-clients')), findsOneWidget);
      expect(find.text('Empleados'), findsWidgets);
      expect(find.text('Mi empresa'), findsNothing);
      expect(find.text('Mis documentos'), findsNothing);
      expect(find.text('Facturacion'), findsNothing);
    });
  });

  // -- CompanyProfile modelo --
  group('CompanyProfile.fromJson', () {
    test('parsea todos los campos', () {
      final profile = CompanyProfile.fromJson({
        'company_code': 'E00001',
        'name': 'Corp',
        'legal_name': 'Corp SL',
        'tax_id': 'B11111111',
        'address': 'Calle 1',
        'postal_code': '08001',
        'city': 'Barcelona',
        'province': 'Barcelona',
        'country': 'ES',
        'phone': '900000000',
        'email': 'corp@corp.es',
        'active': true,
        'profile_synced_at': '2026-08-15T10:00:00Z',
      });

      expect(profile.companyCode, 'E00001');
      expect(profile.legalName, 'Corp SL');
      expect(profile.taxId, 'B11111111');
      expect(profile.profileSyncedAt, '2026-08-15T10:00:00Z');
    });

    test('campos opcionales son null por defecto', () {
      final profile = CompanyProfile.fromJson({
        'company_code': 'E00002',
        'name': 'Minimal',
      });

      expect(profile.legalName, isNull);
      expect(profile.taxId, isNull);
      expect(profile.address, isNull);
      expect(profile.phone, isNull);
      expect(profile.email, isNull);
      expect(profile.active, true);
    });
  });
}
