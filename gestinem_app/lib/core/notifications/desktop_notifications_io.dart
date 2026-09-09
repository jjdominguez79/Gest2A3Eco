import 'dart:io';

import 'package:flutter_local_notifications/flutter_local_notifications.dart';

class DesktopNotifications {
  static const _settings = WindowsInitializationSettings(
    appName: 'Gestinem',
    appUserModelId: 'Gestinem.App.Messaging',
    guid: '6d522a0d-07cf-47f7-875f-162ec47cbb38',
  );

  final FlutterLocalNotificationsPlugin _plugin =
      FlutterLocalNotificationsPlugin();
  bool _initialized = false;
  void Function(String)? _onClick;

  bool get supported => Platform.isWindows;

  Future<void> initialize({required void Function(String) onClick}) async {
    if (!supported) return;
    _onClick = onClick;
    if (_initialized) return;
    final initialized = await _plugin.initialize(
      settings: const InitializationSettings(windows: _settings),
      onDidReceiveNotificationResponse: (response) {
        final payload = response.payload;
        if (payload != null && payload.isNotEmpty) _onClick?.call(payload);
      },
    );
    if (initialized != true) {
      throw StateError('Windows no permitio inicializar las notificaciones');
    }
    _initialized = true;

    final launch = await _plugin.getNotificationAppLaunchDetails();
    final payload = launch?.notificationResponse?.payload;
    if (launch?.didNotificationLaunchApp == true &&
        payload != null &&
        payload.isNotEmpty) {
      _onClick?.call(payload);
    }
  }

  Future<void> show({
    required int id,
    required String title,
    required String body,
    required String payload,
  }) async {
    if (!supported) return;
    if (!_initialized) {
      throw StateError('Las notificaciones de Windows no estan inicializadas');
    }
    await _plugin.show(
      id: id,
      title: title,
      body: body,
      notificationDetails: const NotificationDetails(
        windows: WindowsNotificationDetails(),
      ),
      payload: payload,
    );
  }

  Future<void> cancel(int id) async {
    if (!supported || !_initialized) return;
    await _plugin.cancel(id: id);
  }
}
