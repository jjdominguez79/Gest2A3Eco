import 'package:dio/dio.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:gestinem/features/auth/data/auth_repository.dart';
import 'package:gestinem/features/auth/domain/user_profile.dart';

import 'test_helpers.dart';

void main() {
  test('restaura el perfil staff con token y avatar persistido', () async {
    final adapter = JsonAdapter({
      'id': 'staff-1',
      'name': 'Gestor',
      'email': 'gestor@gestinem.es',
      'role': 'admin',
      'channels': <String>[],
      'avatar_url': '/api/v1/messaging/staff/avatars/staff-1',
    });
    final dio = Dio(BaseOptions(baseUrl: 'https://example.test'))
      ..httpClientAdapter = adapter;
    final repository = AuthRepository(dio);
    const session = AuthSession(
      token: 'saved-token',
      profile: UserProfile(
        id: 'staff-1',
        name: 'Gestor',
        email: 'gestor@gestinem.es',
        type: UserType.staff,
        staffRole: StaffRole.admin,
      ),
    );

    final profile = await repository.currentProfile(session);

    expect(adapter.lastRequest?.headers['Authorization'], 'Bearer saved-token');
    expect(profile.avatarUrl, '/api/v1/messaging/staff/avatars/staff-1');
  });
}
