import 'package:dio/dio.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:gestinem/core/storage/session_storage.dart';
import 'package:gestinem/features/auth/data/auth_repository.dart';
import 'package:gestinem/features/auth/domain/user_profile.dart';
import 'package:gestinem/features/auth/presentation/auth_controller.dart';

class _MemorySessionStorage extends SessionStorage {
  _MemorySessionStorage(this.value);

  AuthSession? value;

  @override
  Future<AuthSession?> read() async => value;

  @override
  Future<void> write(AuthSession session) async => value = session;

  @override
  Future<void> clear() async => value = null;
}

class _ProfileAuthRepository extends AuthRepository {
  _ProfileAuthRepository(this.profile) : super(Dio());

  UserProfile profile;

  @override
  Future<UserProfile> currentProfile(AuthSession session) async => profile;
}

class _ExchangeAuthRepository extends AuthRepository {
  _ExchangeAuthRepository() : super(Dio());

  String? exchangedCode;

  @override
  Future<AuthSession> exchangeStaffCode(String code) async {
    exchangedCode = code;
    return const AuthSession(
      token: 'staff-token',
      profile: UserProfile(
        id: 'staff-1',
        name: 'Gestor',
        email: 'gestor@gestinem.es',
        type: UserType.staff,
        staffRole: StaffRole.admin,
      ),
    );
  }
}

void main() {
  test('lee el codigo staff de la ruta hash web', () {
    expect(
      codigoStaffInicial(
        Uri.parse('https://app.gestinem.es/#/auth/callback?code=abc123'),
      ),
      'abc123',
    );
  });

  const initialProfile = UserProfile(
    id: 'staff-1',
    name: 'Gestor',
    email: 'gestor@gestinem.es',
    type: UserType.staff,
    staffRole: StaffRole.admin,
  );

  test(
    'refreshProfile persiste el avatar actualizado en la sesion segura',
    () async {
      final storage = _MemorySessionStorage(
        const AuthSession(token: 'token', profile: initialProfile),
      );
      final repository = _ProfileAuthRepository(initialProfile);
      final container = ProviderContainer(
        overrides: [
          sessionStorageProvider.overrideWithValue(storage),
          authRepositoryProvider.overrideWithValue(repository),
        ],
      );
      addTearDown(container.dispose);

      final controller = container.read(sessionProvider.notifier);
      await controller.restore();
      repository.profile = const UserProfile(
        id: 'staff-1',
        name: 'Gestor',
        email: 'gestor@gestinem.es',
        type: UserType.staff,
        staffRole: StaffRole.admin,
        avatarUrl: '/api/v1/messaging/staff/avatars/staff-1',
      );

      await controller.refreshProfile();

      expect(
        storage.value?.profile.avatarUrl,
        '/api/v1/messaging/staff/avatars/staff-1',
      );
      expect(
        container.read(sessionProvider).valueOrNull?.profile.avatarUrl,
        '/api/v1/messaging/staff/avatars/staff-1',
      );
    },
  );

  test(
    'restaura el callback web capturado antes de que cambie la URL',
    () async {
      final storage = _MemorySessionStorage(null);
      final repository = _ExchangeAuthRepository();
      const callbackCode = 'codigo-oauth-web-de-prueba';
      final container = ProviderContainer(
        overrides: [
          sessionStorageProvider.overrideWithValue(storage),
          authRepositoryProvider.overrideWithValue(repository),
          sessionProvider.overrideWith(
            (ref) => SessionController(ref, initialStaffAuthCode: callbackCode),
          ),
        ],
      );
      addTearDown(container.dispose);

      await container.read(sessionProvider.notifier).restore();

      expect(repository.exchangedCode, callbackCode);
      expect(container.read(sessionProvider).valueOrNull?.token, 'staff-token');
      expect(storage.value?.profile.type, UserType.staff);
    },
  );

  test('canjea el callback entregado por el router web', () async {
    final storage = _MemorySessionStorage(null);
    final repository = _ExchangeAuthRepository();
    final container = ProviderContainer(
      overrides: [
        sessionStorageProvider.overrideWithValue(storage),
        authRepositoryProvider.overrideWithValue(repository),
        sessionProvider.overrideWith((ref) => SessionController(ref)),
      ],
    );
    addTearDown(container.dispose);

    await container
        .read(sessionProvider.notifier)
        .completeStaffCallback('codigo-entregado-por-router');

    expect(repository.exchangedCode, 'codigo-entregado-por-router');
    expect(container.read(sessionProvider).valueOrNull?.token, 'staff-token');
  });
}
