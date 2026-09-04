import 'package:firebase_messaging/firebase_messaging.dart';
import 'package:flutter/foundation.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../api/api_client.dart';
import '../../features/auth/domain/user_profile.dart';
import 'notifications_service.dart';

// Re-exportamos el enum centralizado para que los importadores de este
// fichero no necesiten importar notifications_service.dart directamente.
export 'notifications_service.dart' show NotificationPermissionState;

final webNotifPermissionProvider =
    StateNotifierProvider<
      WebNotifPermissionNotifier,
      NotificationPermissionState
    >((ref) => WebNotifPermissionNotifier(ref));

/// Gestiona el estado del permiso de notificacion en Flutter Web.
///
/// Solo relevante cuando [kIsWeb] es true. En otras plataformas el estado
/// inicial permanece en [NotificationPermissionState.available] y el banner
/// asociado no se muestra.
class WebNotifPermissionNotifier
    extends StateNotifier<NotificationPermissionState> {
  WebNotifPermissionNotifier(this._ref)
    : super(NotificationPermissionState.available) {
    _detectCurrentState();
  }

  final Ref _ref;

  /// Detecta el estado actual del permiso sin interaccion del usuario.
  Future<void> _detectCurrentState() async {
    try {
      final settings = await FirebaseMessaging.instance
          .getNotificationSettings();
      state = _fromStatus(settings.authorizationStatus);
    } catch (_) {
      // Firebase no esta inicializado todavia o las credenciales son invalidas.
      // Permanecemos en [available] para mostrar el boton de activacion.
    }
  }

  /// Solicita el permiso de notificacion al navegador.
  ///
  /// Solo debe llamarse desde la UI, como respuesta a un gesto explicito.
  /// No llama a este metodo automaticamente al reconstruir widgets.
  Future<void> activate(AuthSession session, ApiClient api) async {
    if (state == NotificationPermissionState.authorized ||
        state == NotificationPermissionState.pending) {
      return;
    }
    state = NotificationPermissionState.pending;
    try {
      final svc = _ref.read(notificationsServiceProvider);
      final granted = await svc.activateWebNotifications(session, api);
      state = granted
          ? NotificationPermissionState.authorized
          : NotificationPermissionState.denied;
    } catch (_) {
      state = NotificationPermissionState.configError;
    }
  }

  /// Actualiza el estado cuando el servicio de notificaciones ya registro el token.
  void markGranted() {
    state = NotificationPermissionState.authorized;
  }

  static NotificationPermissionState _fromStatus(AuthorizationStatus status) =>
      switch (status) {
        AuthorizationStatus.authorized =>
          NotificationPermissionState.authorized,
        AuthorizationStatus.denied => NotificationPermissionState.denied,
        _ => NotificationPermissionState.available,
      };
}
