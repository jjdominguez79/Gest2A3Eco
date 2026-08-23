import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:gestinem/features/auth/domain/user_profile.dart';
import 'package:gestinem/features/auth/presentation/auth_controller.dart';
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

    expect(find.text('Nuevo grupo'), findsOneWidget);
    expect(find.byKey(const Key('new-group-type')), findsOneWidget);
    expect(tester.takeException(), isNull);
  });
}
