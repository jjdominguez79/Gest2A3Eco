import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:gestinem/features/auth/domain/user_profile.dart';
import 'package:gestinem/features/auth/presentation/auth_controller.dart';
import 'package:gestinem/features/campaigns/domain/campaign.dart';
import 'package:gestinem/features/groups/domain/group.dart';
import 'package:gestinem/features/groups/presentation/groups_screen.dart';

import 'test_helpers.dart';

void main() {
  testWidgets('el dialogo de nuevo grupo no desborda en movil', (tester) async {
    await tester.binding.setSurfaceSize(const Size(360, 700));
    addTearDown(() => tester.binding.setSurfaceSize(null));
    const profile = UserProfile(
      id: 'admin',
      name: 'Administrador',
      email: 'admin@gestinem.es',
      type: UserType.staff,
      staffRole: StaffRole.admin,
    );
    const session = AuthSession(token: 'staff-token', profile: profile);

    await tester.pumpWidget(
      ProviderScope(
        overrides: [
          sessionProvider.overrideWith(
            (ref) => FakeSessionController(ref, session),
          ),
          groupsProvider.overrideWith((ref) async => []),
        ],
        child: const MaterialApp(home: GroupsScreen()),
      ),
    );
    await tester.pumpAndSettle();

    expect(find.byIcon(Icons.person_add_alt_1_outlined), findsNothing);
    await tester.tap(find.byIcon(Icons.add));
    await tester.pumpAndSettle();

    expect(find.text('Nuevo grupo o lista'), findsOneWidget);
    expect(find.byKey(const Key('new-group-type')), findsOneWidget);
    expect(tester.takeException(), isNull);
  });

  testWidgets('el administrador puede elegir eliminar un grupo', (
    tester,
  ) async {
    const profile = UserProfile(
      id: 'admin',
      name: 'Administrador',
      email: 'admin@gestinem.es',
      type: UserType.staff,
      staffRole: StaffRole.admin,
    );
    const session = AuthSession(token: 'staff-token', profile: profile);
    const group = MessagingGroup(
      id: 'group-1',
      name: 'Grupo General',
      type: 'staff_chat',
      members: [],
      avatarConfigured: true,
      avatarUrl: '/api/v1/messaging/staff/groups/group-1/avatar',
      avatarVersion: 'version-1',
    );

    await tester.pumpWidget(
      ProviderScope(
        overrides: [
          sessionProvider.overrideWith(
            (ref) => FakeSessionController(ref, session),
          ),
          groupsProvider.overrideWith((ref) async => [group]),
        ],
        child: const MaterialApp(home: GroupsScreen()),
      ),
    );
    await tester.pumpAndSettle();

    await tester.tap(find.byKey(const Key('group-actions-group-1')));
    await tester.pumpAndSettle();
    expect(find.text('Cambiar avatar'), findsOneWidget);
    expect(find.text('Eliminar avatar'), findsOneWidget);
    await tester.tap(find.text('Pasar a histórico'));
    await tester.pumpAndSettle();

    expect(find.text('Pasar grupo a histórico'), findsOneWidget);
    expect(find.byKey(const Key('confirm-delete-group')), findsOneWidget);
    await tester.tap(find.text('Cancelar'));
    await tester.pumpAndSettle();
    expect(find.text('Pasar grupo a histórico'), findsNothing);
  });

  testWidgets('un grupo historico se muestra sin acciones de edicion', (
    tester,
  ) async {
    const profile = UserProfile(
      id: 'admin',
      name: 'Administrador',
      email: 'admin@gestinem.es',
      type: UserType.staff,
      staffRole: StaffRole.admin,
    );
    const session = AuthSession(token: 'staff-token', profile: profile);
    const group = MessagingGroup(
      id: 'group-old',
      name: 'Equipo Contable / Fiscal',
      type: 'staff_chat',
      members: [],
      active: false,
      threadId: 'thread-old',
    );

    await tester.pumpWidget(
      ProviderScope(
        overrides: [
          sessionProvider.overrideWith(
            (ref) => FakeSessionController(ref, session),
          ),
          groupsProvider.overrideWith((ref) async => [group]),
        ],
        child: const MaterialApp(home: GroupsScreen()),
      ),
    );
    await tester.pumpAndSettle();

    expect(find.byKey(const Key('historical-groups-archive')), findsOneWidget);
    expect(find.text('Archivo de grupos históricos'), findsOneWidget);
    expect(find.text('Equipo Contable / Fiscal'), findsOneWidget);
    expect(find.textContaining('Histórico · solo lectura'), findsOneWidget);
    expect(find.byKey(const Key('group-actions-group-old')), findsNothing);
  });

  testWidgets('el administrador puede asignar clientes a una lista', (
    tester,
  ) async {
    const profile = UserProfile(
      id: 'admin',
      name: 'Administrador',
      email: 'admin@gestinem.es',
      type: UserType.staff,
      staffRole: StaffRole.admin,
    );
    const session = AuthSession(token: 'staff-token', profile: profile);
    const group = MessagingGroup(
      id: 'list-1',
      name: 'Clientes trimestrales',
      type: 'client_list',
      members: [
        GroupMember(
          id: 'member-1',
          memberType: 'client',
          memberId: 'client-1',
          role: 'member',
        ),
      ],
    );

    await tester.pumpWidget(
      ProviderScope(
        overrides: [
          sessionProvider.overrideWith(
            (ref) => FakeSessionController(ref, session),
          ),
          groupsProvider.overrideWith((ref) async => [group]),
          clientListTargetsProvider.overrideWith(
            (ref) async => const [
              CampaignClientTarget(
                id: 'client-1',
                name: 'María',
                company: 'Empresa Uno',
                companyCode: 'E00001',
                email: 'maria@example.test',
              ),
              CampaignClientTarget(
                id: 'client-2',
                name: 'Pedro',
                company: 'Empresa Dos',
                companyCode: 'E00002',
                email: 'pedro@example.test',
              ),
            ],
          ),
        ],
        child: const MaterialApp(home: GroupsScreen()),
      ),
    );
    await tester.pumpAndSettle();

    expect(find.byKey(const Key('client-lists-section')), findsOneWidget);
    expect(find.text('Clientes trimestrales'), findsOneWidget);
    await tester.tap(find.byKey(const Key('group-list-1')));
    await tester.pumpAndSettle();

    expect(find.text('Clientes de Clientes trimestrales'), findsOneWidget);
    expect(
      find.byKey(const Key('client-list-member-client-1')),
      findsOneWidget,
    );
    expect(
      find.byKey(const Key('client-list-member-client-2')),
      findsOneWidget,
    );
    final first = tester.widget<CheckboxListTile>(
      find.byKey(const Key('client-list-member-client-1')),
    );
    expect(first.value, isTrue);
    expect(find.byKey(const Key('save-client-list')), findsOneWidget);
    await tester.tap(find.text('Cancelar'));
    await tester.pumpAndSettle();
  });
}
