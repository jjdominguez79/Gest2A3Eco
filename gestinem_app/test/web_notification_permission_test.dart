import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:gestinem/core/api/api_client.dart';
import 'package:gestinem/core/notifications/notifications_service.dart';
import 'package:gestinem/core/notifications/web_permission_state.dart';
import 'package:gestinem/features/auth/domain/user_profile.dart';
import 'package:gestinem/features/auth/presentation/auth_controller.dart';

import 'test_helpers.dart';

// ---------------------------------------------------------------------------
// Fakes
// ---------------------------------------------------------------------------

class _FakeNotificationsService extends NotificationsService {
  bool initializeCalled = false;
  bool activateCalled = false;
  bool activateResult = true;

  @override
  Future<void> initialize(AuthSession session, ApiClient api) async {
    initializeCalled = true;
  }

  @override
  Future<bool> activateWebNotifications(
    AuthSession session,
    ApiClient api,
  ) async {
    activateCalled = true;
    return activateResult;
  }
}

class _ThrowingNotificationsService extends NotificationsService {
  @override
  Future<bool> activateWebNotifications(
    AuthSession session,
    ApiClient api,
  ) async {
    throw Exception('Firebase no configurado');
  }
}

class _CountingNotificationsService extends NotificationsService {
  int initCount = 0;

  @override
  Future<void> initialize(AuthSession session, ApiClient api) async {
    // Simula la proteccion contra inicializacion concurrente.
    if (initCount > 0) return;
    initCount++;
    await Future.delayed(const Duration(milliseconds: 10));
  }
}

// ---------------------------------------------------------------------------
// Helper
// ---------------------------------------------------------------------------

ProviderContainer _makeContainer(NotificationsService svc) {
  return ProviderContainer(overrides: [
    notificationsServiceProvider.overrideWithValue(svc),
    sessionProvider.overrideWith((ref) => FakeSessionController(ref)),
  ]);
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

void main() {
  group('WebNotifPermissionNotifier', () {
    test('estado inicial es available cuando no hay Firebase', () {
      // En unit test no hay Firebase inicializado; el notifier queda en available.
      final container = _makeContainer(_FakeNotificationsService());
      addTearDown(container.dispose);

      expect(
        container.read(webNotifPermissionProvider),
        NotificationPermissionState.available,
      );
    });

    test('activate llega a authorized cuando el servicio devuelve true', () async {
      final svc = _FakeNotificationsService()..activateResult = true;
      final container = _makeContainer(svc);
      addTearDown(container.dispose);

      final api = container.read(apiClientProvider);
      await container.read(webNotifPermissionProvider.notifier).activate(
            testSession,
            api,
          );

      expect(
        container.read(webNotifPermissionProvider),
        NotificationPermissionState.authorized,
      );
      expect(svc.activateCalled, isTrue);
    });

    test('activate llega a denied cuando el servicio devuelve false', () async {
      final svc = _FakeNotificationsService()..activateResult = false;
      final container = _makeContainer(svc);
      addTearDown(container.dispose);

      final api = container.read(apiClientProvider);
      await container.read(webNotifPermissionProvider.notifier).activate(
            testSession,
            api,
          );

      expect(
        container.read(webNotifPermissionProvider),
        NotificationPermissionState.denied,
      );
    });

    test('activate llega a configError si el servicio lanza excepcion', () async {
      final container = _makeContainer(_ThrowingNotificationsService());
      addTearDown(container.dispose);

      final api = container.read(apiClientProvider);
      await container.read(webNotifPermissionProvider.notifier).activate(
            testSession,
            api,
          );

      expect(
        container.read(webNotifPermissionProvider),
        NotificationPermissionState.configError,
      );
    });

    test('activate no hace nada si ya esta authorized', () async {
      final svc = _FakeNotificationsService()..activateResult = true;
      final container = _makeContainer(svc);
      addTearDown(container.dispose);

      // Forzar estado authorized primero.
      container.read(webNotifPermissionProvider.notifier).markGranted();
      expect(
        container.read(webNotifPermissionProvider),
        NotificationPermissionState.authorized,
      );

      final api = container.read(apiClientProvider);
      await container.read(webNotifPermissionProvider.notifier).activate(
            testSession,
            api,
          );

      // No debe haber llamado al servicio.
      expect(svc.activateCalled, isFalse);
    });

    test('markGranted actualiza estado a authorized', () {
      final container = _makeContainer(_FakeNotificationsService());
      addTearDown(container.dispose);

      container.read(webNotifPermissionProvider.notifier).markGranted();

      expect(
        container.read(webNotifPermissionProvider),
        NotificationPermissionState.authorized,
      );
    });

    test('renovacion de token no duplica inicializacion', () async {
      // NotificationsService protege contra inicializacion concurrente.
      final svc = _CountingNotificationsService();
      final container = _makeContainer(svc);
      addTearDown(container.dispose);

      final api = container.read(apiClientProvider);

      // Dos llamadas concurrentes a initialize.
      await Future.wait([
        svc.initialize(testSession, api),
        svc.initialize(testSession, api),
      ]);

      // La inicializacion real debe haber ocurrido exactamente una vez.
      expect(svc.initCount, 1);
    });

    test('permiso concedido: activate devuelve true y estado es authorized', () async {
      final svc = _FakeNotificationsService()..activateResult = true;
      final container = _makeContainer(svc);
      addTearDown(container.dispose);

      final api = container.read(apiClientProvider);
      await container.read(webNotifPermissionProvider.notifier).activate(
            testSession,
            api,
          );

      expect(
        container.read(webNotifPermissionProvider),
        NotificationPermissionState.authorized,
      );
    });

    test('permiso denegado: activate devuelve false y estado es denied', () async {
      final svc = _FakeNotificationsService()..activateResult = false;
      final container = _makeContainer(svc);
      addTearDown(container.dispose);

      final api = container.read(apiClientProvider);
      await container.read(webNotifPermissionProvider.notifier).activate(
            testSession,
            api,
          );

      expect(
        container.read(webNotifPermissionProvider),
        NotificationPermissionState.denied,
      );
    });
  });
}
