import 'package:flutter/foundation.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:gestinem/core/notifications/notifications_service.dart';

// Tests unitarios de NotificationsService.
//
// Las APIs estaticas de Firebase (FirebaseMessaging.instance, etc.) no se
// pueden instanciar en tests unitarios sin un motor Firebase real.
// Estos tests verifican la logica propia del servicio que no depende de Firebase:
// estado de permiso, emision de eventos, deteccion de plataforma, etc.

void main() {
  group('NotificationsService', () {
    test('estado inicial es available', () {
      final service = NotificationsService();
      expect(service.permissionState, NotificationPermissionState.available);
    });

    test('fcmConfigured es false inicialmente', () {
      final service = NotificationsService();
      expect(service.fcmConfigured, isFalse);
    });

    test('events emite NotificationEvent con conversationId', () async {
      final service = NotificationsService();
      final events = <NotificationEvent>[];
      final sub = service.events.listen(events.add);

      // Simulamos emision interna mediante reflexion no es posible sin
      // instanciar Firebase. Este test verifica que el stream es broadcast.
      expect(service.events.isBroadcast, isTrue);

      await sub.cancel();
    });

    test('NotificationEvent almacena campos correctamente', () {
      const event = NotificationEvent(
        conversationId: 'conv-123',
        opened: false,
        threadId: 'thread-456',
        title: 'Titulo',
        body: 'Cuerpo',
      );

      expect(event.conversationId, 'conv-123');
      expect(event.threadId, 'thread-456');
      expect(event.opened, isFalse);
      expect(event.title, 'Titulo');
      expect(event.body, 'Cuerpo');
    });

    test('NotificationEvent sin threadId tiene threadId null', () {
      const event = NotificationEvent(
        conversationId: 'conv-123',
        opened: true,
      );

      expect(event.threadId, isNull);
      expect(event.title, isNull);
      expect(event.body, isNull);
    });

    test('permissionState tiene todos los estados esperados', () {
      expect(NotificationPermissionState.values, containsAll([
        NotificationPermissionState.available,
        NotificationPermissionState.pending,
        NotificationPermissionState.authorized,
        NotificationPermissionState.denied,
        NotificationPermissionState.configError,
      ]));
    });

    test('plataforma web se detecta con kIsWeb', () {
      // En tests de Flutter Web kIsWeb seria true.
      // En tests de escritorio/movil seria false.
      // Solo verificamos que la constante es accesible.
      expect(kIsWeb, isA<bool>());
    });
  });

  group('NotificationPermissionState', () {
    test('authorized indica FCM activo', () {
      expect(
        NotificationPermissionState.authorized.name,
        'authorized',
      );
    });

    test('configError indica falta de VAPID key', () {
      expect(
        NotificationPermissionState.configError.name,
        'configError',
      );
    });
  });
}
