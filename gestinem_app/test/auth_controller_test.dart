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

void main() {
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
}
