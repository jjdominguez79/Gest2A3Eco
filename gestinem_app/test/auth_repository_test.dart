import 'package:dio/dio.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:gestinem/features/auth/data/auth_repository.dart';
import 'package:gestinem/features/auth/domain/user_profile.dart';

import 'test_helpers.dart';

void main() {
  test('el retorno web elimina query y fragmento de la ruta actual', () {
    final redirect = construirRetornoWeb(
      Uri.parse('https://app.gestinem.es/#/login'),
    );

    expect(redirect, 'https://app.gestinem.es/auth/callback');
  });

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

  test('accede como personal de revision mediante contraseña', () async {
    final adapter = JsonAdapter({
      'token': 'review-token',
      'staff': {
        'id': 'review-1',
        'name': 'Personal de revision',
        'email': 'stores.staff.review@gestinem.es',
        'role': 'empleado',
        'channels': <String>[],
      },
    });
    final dio = Dio(BaseOptions(baseUrl: 'https://example.test'))
      ..httpClientAdapter = adapter;
    final repository = AuthRepository(dio);

    final session = await repository.loginStaffWithPassword(
      ' stores.staff.review@gestinem.es ',
      'clave-segura',
    );

    expect(adapter.lastRequest?.path, '/staff-auth/review-login');
    expect(adapter.lastRequest?.data, {
      'email': 'stores.staff.review@gestinem.es',
      'password': 'clave-segura',
    });
    expect(session.profile.type, UserType.staff);
    expect(session.profile.staffRole, StaffRole.empleado);
    expect(session.token, 'review-token');
  });
}
