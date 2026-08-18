import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:gestinem/features/auth/domain/user_profile.dart';
import 'package:gestinem/features/auth/presentation/auth_controller.dart';
import 'package:gestinem/features/empleados/domain/empleado_despacho.dart';
import 'package:gestinem/features/empleados/presentation/empleados_screen.dart';

import 'test_helpers.dart';

void main() {
  testWidgets('administrador puede abrir la configuracion de empleados', (
    tester,
  ) async {
    const admin = UserProfile(
      id: 'admin-1',
      name: 'Juan Jose',
      email: 'juan@gestinem.es',
      type: UserType.staff,
      staffRole: StaffRole.admin,
    );
    const session = AuthSession(token: 'staff-token', profile: admin);
    const empleado = EmpleadoDespacho(
      id: 'empleado-1',
      nombre: 'Ana Fiscal',
      email: 'ana@gestinem.es',
      rol: 'empleado',
      activo: true,
      vinculado: true,
      aliasChat: 'Ana',
      avatarConfigurado: false,
      canales: {'fiscal'},
    );

    await tester.pumpWidget(
      ProviderScope(
        overrides: [
          sessionProvider.overrideWith(
            (ref) => FakeSessionController(ref, session),
          ),
          empleadosProvider.overrideWith((ref) async => [empleado]),
        ],
        child: const MaterialApp(home: EmpleadosScreen()),
      ),
    );
    await tester.pumpAndSettle();

    expect(find.text('Empleados del despacho'), findsOneWidget);
    expect(find.text('Ana'), findsOneWidget);
    expect(find.byKey(const Key('add-employee')), findsOneWidget);
    expect(find.byKey(const Key('employee-empleado-1')), findsOneWidget);
  });
}
