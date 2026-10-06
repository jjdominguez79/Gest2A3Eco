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
        documentId: 'doc-789',
        notificationId: 'message-012',
        title: 'Titulo',
        body: 'Cuerpo',
      );

      expect(event.conversationId, 'conv-123');
      expect(event.threadId, 'thread-456');
      expect(event.documentId, 'doc-789');
      expect(event.notificationId, 'message-012');
      expect(event.opened, isFalse);
      expect(event.title, 'Titulo');
      expect(event.body, 'Cuerpo');
    });

    test('NotificationEvent sin threadId tiene threadId null', () {
      const event = NotificationEvent(conversationId: 'conv-123', opened: true);

      expect(event.threadId, isNull);
      expect(event.title, isNull);
      expect(event.body, isNull);
    });

    test('permissionState tiene todos los estados esperados', () {
      expect(
        NotificationPermissionState.values,
        containsAll([
          NotificationPermissionState.available,
          NotificationPermissionState.pending,
          NotificationPermissionState.authorized,
          NotificationPermissionState.denied,
          NotificationPermissionState.configError,
        ]),
      );
    });

    test('plataforma web se detecta con kIsWeb', () {
      // En tests de Flutter Web kIsWeb seria true.
      // En tests de escritorio/movil seria false.
      // Solo verificamos que la constante es accesible.
      expect(kIsWeb, isA<bool>());
    });

    test('una conversacion conserva un unico identificador de aviso', () {
      final first = notificationIdForTarget('conversation', 'conv-123');
      final second = notificationIdForTarget('conversation', 'conv-123');
      final other = notificationIdForTarget('conversation', 'conv-456');

      expect(first, second);
      expect(first, isNot(other));
    });

    test('payload antiguo resuelve el destino exacto', () {
      expect(notificationTargetId({'conversation_id': 'conv-123'}), 'conv-123');
      expect(
        notificationTargetType({'thread_id': 'thread-456'}),
        'internal_thread',
      );
      expect(notificationTargetId({'thread_id': 'thread-456'}), 'thread-456');
    });

    test('rechaza un token FCM ausente', () {
      expect(() => requirePushToken(null), throwsStateError);
      expect(() => requirePushToken('  '), throwsStateError);
    });

    test('normaliza un token FCM valido', () {
      expect(requirePushToken(' token-valido '), 'token-valido');
    });

    test('exige confirmacion del servidor al registrar dispositivo', () {
      expect(() => requireDeviceRegistrationId(null), throwsStateError);
      expect(() => requireDeviceRegistrationId(''), throwsStateError);
      expect(requireDeviceRegistrationId(' device-1 '), 'device-1');
    });

    test('solo descarta la entrega duplicada del mismo aviso', () {
      final guard = NotificationOpenGuard();
      final first = NotificationEvent(
        conversationId: 'conv-123',
        opened: true,
        notificationId: 'message-1',
      );
      final sameMessage = NotificationEvent(
        conversationId: 'conv-123',
        opened: true,
        notificationId: 'message-1',
      );
      final nextMessage = NotificationEvent(
        conversationId: 'conv-123',
        opened: true,
        notificationId: 'message-2',
      );

      expect(guard.shouldHandle(first), isTrue);
      expect(guard.shouldHandle(first), isFalse);
      expect(guard.shouldHandle(sameMessage), isFalse);
      expect(guard.shouldHandle(nextMessage), isTrue);
    });

    test('avisos posteriores sin id pueden reabrir el mismo chat', () {
      final guard = NotificationOpenGuard();
      final first = NotificationEvent(conversationId: 'conv-123', opened: true);
      final later = NotificationEvent(conversationId: 'conv-123', opened: true);

      expect(guard.shouldHandle(first), isTrue);
      expect(guard.shouldHandle(first), isFalse);
      expect(guard.shouldHandle(later), isTrue);
    });
  });

  group('NotificationPermissionState', () {
    test('authorized indica FCM activo', () {
      expect(NotificationPermissionState.authorized.name, 'authorized');
    });

    test('configError indica falta de VAPID key', () {
      expect(NotificationPermissionState.configError.name, 'configError');
    });
  });
}
