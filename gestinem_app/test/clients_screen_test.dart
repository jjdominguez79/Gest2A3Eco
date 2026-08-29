import 'package:dio/dio.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:gestinem/core/api/api_client.dart';
import 'package:gestinem/features/auth/domain/user_profile.dart';
import 'package:gestinem/features/auth/presentation/auth_controller.dart';
import 'package:gestinem/features/messaging/domain/client_organization.dart';
import 'package:gestinem/features/messaging/presentation/client_detail_screen.dart';
import 'package:gestinem/features/messaging/presentation/clients_screen.dart';
import 'package:gestinem/features/messaging/presentation/messaging_providers.dart';

import 'test_helpers.dart';

void main() {
  const profile = UserProfile(
    id: 'admin',
    name: 'Administrador',
    email: 'admin@gestinem.es',
    type: UserType.staff,
    staffRole: StaffRole.admin,
  );
  const session = AuthSession(token: 'staff-token', profile: profile);

  testWidgets('Clientes muestra todos y filtra por estado de acceso', (
    tester,
  ) async {
    const rows = [
      ClientOrganization(
        companyCode: 'E00001',
        name: 'Cliente activo',
        active: true,
        accessStatus: 'active',
        accessActive: true,
        hasAcceptedAccess: true,
        clientCount: 1,
      ),
      ClientOrganization(
        companyCode: 'E00002',
        name: 'Cliente pendiente',
        active: true,
        accessStatus: 'pending',
        accessActive: false,
        hasAcceptedAccess: false,
        clientCount: 1,
      ),
      ClientOrganization(
        companyCode: 'E00003',
        name: 'Cliente sin invitar',
        active: true,
        accessStatus: 'not_invited',
        accessActive: false,
        hasAcceptedAccess: false,
        clientCount: 0,
      ),
    ];
    final api = ApiClient(
      dio: Dio(BaseOptions(baseUrl: 'https://example.test'))
        ..httpClientAdapter = JsonAdapter(<Object>[]),
      tokenProvider: () => session.token,
    );
    await tester.pumpWidget(
      ProviderScope(
        overrides: [
          sessionProvider.overrideWith(
            (ref) => FakeSessionController(ref, session),
          ),
          apiClientProvider.overrideWithValue(api),
          clientOrganizationsProvider.overrideWith((ref) async => rows),
        ],
        child: const MaterialApp(home: ClientsScreen()),
      ),
    );
    await tester.pumpAndSettle();

    expect(find.byKey(const Key('client-E00001')), findsOneWidget);
    expect(find.byKey(const Key('client-E00002')), findsOneWidget);
    expect(find.byKey(const Key('client-E00003')), findsOneWidget);
    expect(find.byKey(const Key('clients-back-button')), findsOneWidget);

    await tester.tap(find.byKey(const Key('clients-filter-pending')));
    await tester.pump();
    expect(find.byKey(const Key('client-E00001')), findsNothing);
    expect(find.byKey(const Key('client-E00002')), findsOneWidget);
    expect(find.byKey(const Key('client-E00003')), findsNothing);
  });

  testWidgets('Ficha pendiente muestra contacto, chat y retirada', (
    tester,
  ) async {
    await tester.binding.setSurfaceSize(const Size(800, 1200));
    addTearDown(() => tester.binding.setSurfaceSize(null));
    final expiresAt = DateTime(2026, 8, 30, 12);
    final row = ClientOrganization(
      companyCode: 'E00002',
      name: 'Cliente pendiente',
      active: true,
      accessStatus: 'pending',
      accessActive: false,
      hasAcceptedAccess: false,
      clientCount: 1,
      contactName: 'Ana Cliente',
      contactEmail: 'ana@example.test',
      invitationExpiresAt: expiresAt,
    );
    final api = ApiClient(
      dio: Dio(BaseOptions(baseUrl: 'https://example.test'))
        ..httpClientAdapter = JsonAdapter(<Object>[]),
      tokenProvider: () => session.token,
    );
    await tester.pumpWidget(
      ProviderScope(
        overrides: [
          sessionProvider.overrideWith(
            (ref) => FakeSessionController(ref, session),
          ),
          apiClientProvider.overrideWithValue(api),
          clientOrganizationsProvider.overrideWith((ref) async => [row]),
          orgFeaturesProvider(
            'E00002',
          ).overrideWith((ref) async => const OrganizationFeatures()),
        ],
        child: const MaterialApp(
          home: MediaQuery(
            data: MediaQueryData(padding: EdgeInsets.only(bottom: 32)),
            child: ClientDetailScreen(companyCode: 'E00002'),
          ),
        ),
      ),
    );
    await tester.pumpAndSettle();

    final listView = tester.widget<ListView>(find.byType(ListView));
    expect(listView.padding?.resolve(TextDirection.ltr).bottom, 52);
    expect(find.text('Ana Cliente'), findsOneWidget);
    expect(find.text('ana@example.test'), findsOneWidget);
    expect(find.byKey(const Key('client-open-direct')), findsOneWidget);
    expect(find.byKey(const Key('client-withdraw-invite')), findsOneWidget);
    expect(find.byKey(const Key('client-disable-access')), findsNothing);
  });
}
