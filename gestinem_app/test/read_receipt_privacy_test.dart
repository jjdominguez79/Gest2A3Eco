import 'package:dio/dio.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:gestinem/core/api/api_client.dart';
import 'package:gestinem/features/auth/domain/user_profile.dart';
import 'package:gestinem/features/auth/presentation/auth_controller.dart';
import 'package:gestinem/features/messaging/presentation/messaging_providers.dart';
import 'package:gestinem/features/profile/data/profile_repository.dart';
import 'package:gestinem/features/profile/presentation/profile_screen.dart';

import 'test_helpers.dart';

class _RepositorioPrivacidad extends ProfileRepository {
  _RepositorioPrivacidad() : super(ApiClient(tokenProvider: () => null));
  bool clientes = false;
  bool empleados = true;
  bool fallar = false;

  @override
  Future<void> actualizarPrivacidadLecturas({
    bool? clientes,
    bool? empleados,
  }) async {
    if (fallar) throw Exception('No se pudo guardar');
    if (clientes != null) this.clientes = clientes;
    if (empleados != null) this.empleados = empleados;
  }
}

class _SesionPrivacidad extends FakeSessionController {
  _SesionPrivacidad(Ref ref, this.repositorio, UserProfile perfil)
    : super(ref, AuthSession(token: 'test', profile: perfil));

  final _RepositorioPrivacidad repositorio;

  @override
  Future<void> refreshProfile() async {
    final perfil = state.valueOrNull!.profile;
    state = AsyncData(
      AuthSession(
        token: 'test',
        profile: UserProfile.fromJson({
          ...perfil.toJson(),
          'mostrar_lecturas_clientes': repositorio.clientes,
          'mostrar_lecturas_empleados': repositorio.empleados,
        }, UserType.staff),
      ),
    );
  }
}

void main() {
  const admin = UserProfile(
    id: 'admin',
    name: 'Admin',
    email: 'admin@test.es',
    type: UserType.staff,
    staffRole: StaffRole.admin,
    mostrarEstadosMensajes: false,
    mostrarLecturasClientes: false,
    mostrarLecturasEmpleados: true,
  );

  test('perfil conserva privacidad y administrador siempre ve estados', () {
    final guardada = AuthSession(token: 'test', profile: admin);
    final perfil = AuthSession.fromJson(guardada.toJson()).profile;
    expect(perfil.verEstadosMensajes, isTrue);
    expect(perfil.mostrarLecturasClientes, isFalse);
    expect(perfil.mostrarLecturasEmpleados, isTrue);
    final antiguo = UserProfile.fromJson({
      'id': 'admin',
      'role': 'admin',
      'mostrar_estados_mensajes': false,
    }, UserType.staff);
    expect(antiguo.verEstadosMensajes, isTrue);
    expect(antiguo.mostrarLecturasClientes, isTrue);
    expect(antiguo.mostrarLecturasEmpleados, isTrue);
  });

  test('repositorio envia solo la preferencia cambiada', () async {
    final adapter = JsonAdapter({'ok': true});
    final dio = Dio(BaseOptions(baseUrl: 'https://test.es'))
      ..httpClientAdapter = adapter;
    final repository = ProfileRepository(
      ApiClient(dio: dio, tokenProvider: () => 'test'),
    );
    await repository.actualizarPrivacidadLecturas(clientes: false);
    expect(adapter.lastRequest!.path, '/staff/me');
    expect(adapter.lastRequest!.method, 'PATCH');
    expect(adapter.lastRequest!.data, {'mostrar_lecturas_clientes': false});
    await repository.actualizarPrivacidadLecturas(empleados: false);
    expect(adapter.lastRequest!.data, {'mostrar_lecturas_empleados': false});
  });

  testWidgets('administrador configura clientes y empleados por separado', (
    tester,
  ) async {
    final repo = _RepositorioPrivacidad();
    await tester.pumpWidget(
      ProviderScope(
        overrides: [
          sessionProvider.overrideWith(
            (ref) => _SesionPrivacidad(ref, repo, admin),
          ),
          profileRepositoryProvider.overrideWithValue(repo),
        ],
        child: const MaterialApp(home: ProfileScreen()),
      ),
    );
    await tester.pumpAndSettle();
    expect(find.text('Mostrar estados de mis mensajes'), findsNothing);
    final clientes = find.byKey(const Key('mostrar-lecturas-clientes'));
    final empleados = find.byKey(const Key('mostrar-lecturas-empleados'));
    await tester.scrollUntilVisible(clientes, 200);
    expect(tester.widget<SwitchListTile>(clientes).value, isFalse);
    await tester.tap(clientes);
    await tester.pumpAndSettle();
    expect(repo.clientes, isTrue);
    expect(repo.empleados, isTrue);
    await tester.scrollUntilVisible(empleados, 200);
    await tester.tap(empleados);
    await tester.pumpAndSettle();
    expect(repo.clientes, isTrue);
    expect(repo.empleados, isFalse);
    expect(tester.widget<SwitchListTile>(empleados).value, isFalse);
  });

  testWidgets('fallo de guardado conserva la preferencia anterior', (
    tester,
  ) async {
    final repo = _RepositorioPrivacidad()..fallar = true;
    await tester.pumpWidget(
      ProviderScope(
        overrides: [
          sessionProvider.overrideWith(
            (ref) => _SesionPrivacidad(ref, repo, admin),
          ),
          profileRepositoryProvider.overrideWithValue(repo),
        ],
        child: const MaterialApp(home: ProfileScreen()),
      ),
    );
    final clientes = find.byKey(const Key('mostrar-lecturas-clientes'));
    await tester.scrollUntilVisible(clientes, 200);
    await tester.tap(clientes);
    await tester.pumpAndSettle();
    expect(tester.widget<SwitchListTile>(clientes).value, isFalse);
    expect(tester.widget<SwitchListTile>(clientes).onChanged, isNotNull);
    expect(find.byType(SnackBar), findsOneWidget);
  });

  testWidgets('empleado no puede configurar privacidad del administrador', (
    tester,
  ) async {
    const employee = UserProfile(
      id: 'employee',
      name: 'Empleado',
      email: 'e@test.es',
      type: UserType.staff,
      staffRole: StaffRole.empleado,
    );
    await tester.pumpWidget(
      ProviderScope(
        overrides: [
          sessionProvider.overrideWith(
            (ref) => FakeSessionController(
              ref,
              const AuthSession(token: 'test', profile: employee),
            ),
          ),
        ],
        child: const MaterialApp(home: ProfileScreen()),
      ),
    );
    expect(find.byKey(const Key('mostrar-lecturas-clientes')), findsNothing);
    expect(find.byKey(const Key('mostrar-lecturas-empleados')), findsNothing);
    expect(find.text('Mostrar estados de mis mensajes'), findsOneWidget);
  });
}
