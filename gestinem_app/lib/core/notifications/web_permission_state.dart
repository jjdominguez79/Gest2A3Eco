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
      // El permiso del navegador no demuestra que exista un token FCM ni que
      // el backend lo haya registrado. Solo el servicio puede marcar authorized.
      applyDetectedBrowserPermission(settings.authorizationStatus);
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
          : switch (svc.permissionState) {
              NotificationPermissionState.denied =>
                NotificationPermissionState.denied,
              _ => NotificationPermissionState.configError,
            };
    } catch (_) {
      state = NotificationPermissionState.configError;
    }
  }

  /// Actualiza el estado cuando el servicio de notificaciones ya registro el token.
  void markGranted() {
    state = NotificationPermissionState.authorized;
  }

  /// Sincroniza el resultado real de token + alta en el backend.
  void syncRegistration(NotificationPermissionState value) {
    state = value;
  }

  /// Aplica la lectura inicial solo si no ha comenzado otra operacion.
  ///
  /// La consulta al navegador es asincrona y puede terminar despues de que el
  /// token ya se haya registrado. En ese caso no debe sobrescribir authorized.
  @visibleForTesting
  void applyDetectedBrowserPermission(AuthorizationStatus status) {
    if (state != NotificationPermissionState.available) return;
    state = status == AuthorizationStatus.denied
        ? NotificationPermissionState.denied
        : NotificationPermissionState.available;
  }
}
