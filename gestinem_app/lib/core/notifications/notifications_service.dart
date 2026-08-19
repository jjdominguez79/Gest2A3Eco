import 'dart:async';

import 'package:flutter/foundation.dart';
import 'package:firebase_core/firebase_core.dart';
import 'package:firebase_messaging/firebase_messaging.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:package_info_plus/package_info_plus.dart';

import '../api/api_client.dart';
import '../../features/auth/domain/user_profile.dart';
import 'desktop_notifications.dart';

final notificationsServiceProvider = Provider<NotificationsService>(
  (ref) => NotificationsService(),
);

class NotificationEvent {
  const NotificationEvent({
    required this.conversationId,
    required this.opened,
    this.threadId,
  });

  final String conversationId;
  final String? threadId;
  final bool opened;
}

class NotificationsService {
  final DesktopNotifications _desktop = DesktopNotifications();
  String? _owner;
  String? _deviceId;
  StreamSubscription<String>? _tokenRefresh;
  final _events = StreamController<NotificationEvent>.broadcast();
  bool _messageListenersConfigured = false;

  Stream<NotificationEvent> get events => _events.stream;

  Future<void> initialize(AuthSession session, ApiClient api) async {
    if (_desktop.supported) {
      if (_owner == _ownerFor(session)) return;
      try {
        await _desktop.initialize();
        _owner = _ownerFor(session);
      } catch (error, stackTrace) {
        debugPrint(
          'No se pudieron activar las notificaciones de Windows: '
          '$error\n$stackTrace',
        );
      }
      return;
    }
    if (!_supported || _owner == _ownerFor(session)) return;
    try {
      if (Firebase.apps.isEmpty) await Firebase.initializeApp();
      final messaging = FirebaseMessaging.instance;
      await _configureMessageListeners(messaging);
      await messaging.requestPermission();
      final token = await messaging.getToken();
      if (token == null) return;
      await _register(session, api, token);
      _owner = _ownerFor(session);
      await _tokenRefresh?.cancel();
      _tokenRefresh = messaging.onTokenRefresh.listen(
        (refreshed) => unawaited(_register(session, api, refreshed)),
      );
    } catch (error, stackTrace) {
      // Firebase es opcional en desarrollo y no debe impedir usar REST/WebSocket.
      debugPrint(
        'No se pudieron activar las notificaciones: $error\n$stackTrace',
      );
    }
  }

  Future<void> showDesktop({
    required String title,
    required String body,
    required void Function() onClick,
  }) async {
    try {
      await _desktop.show(title: title, body: body, onClick: onClick);
    } catch (error, stackTrace) {
      debugPrint(
        'No se pudo mostrar la notificación de Windows: $error\n$stackTrace',
      );
    }
  }

  Future<void> _configureMessageListeners(FirebaseMessaging messaging) async {
    if (_messageListenersConfigured) return;
    _messageListenersConfigured = true;
    FirebaseMessaging.onMessage.listen(
      (message) => _emit(message, opened: false),
    );
    FirebaseMessaging.onMessageOpenedApp.listen(
      (message) => _emit(message, opened: true),
    );
    final initial = await messaging.getInitialMessage();
    if (initial != null) _emit(initial, opened: true);
  }

  void _emit(RemoteMessage message, {required bool opened}) {
    final conversationId = message.data['conversation_id']?.toString() ?? '';
    final threadId = message.data['thread_id']?.toString();
    if (conversationId.isEmpty && (threadId == null || threadId.isEmpty)) {
      return;
    }
    _events.add(
      NotificationEvent(
        conversationId: conversationId,
        threadId: threadId,
        opened: opened,
      ),
    );
  }

  Future<void> unregister(AuthSession session, ApiClient api) async {
    final deviceId = _deviceId;
    if (deviceId != null && _owner == _ownerFor(session)) {
      await api.dio.delete<void>(
        '/${session.profile.type.name}/app-devices/$deviceId',
      );
    }
    await _tokenRefresh?.cancel();
    _tokenRefresh = null;
    _owner = null;
    _deviceId = null;
  }

  Future<void> _register(
    AuthSession session,
    ApiClient api,
    String token,
  ) async {
    final packageInfo = await PackageInfo.fromPlatform();
    final response = await api.dio.put<Map<String, dynamic>>(
      '/${session.profile.type.name}/app-devices',
      data: {
        'platform': _platform,
        'push_token': token,
        'device_name': '',
        'app_version': '${packageInfo.version}+${packageInfo.buildNumber}',
      },
    );
    _deviceId = response.data?['id'] as String?;
  }

  String _ownerFor(AuthSession session) =>
      '${session.profile.type.name}:${session.profile.id}';

  bool get _supported =>
      kIsWeb ||
      defaultTargetPlatform == TargetPlatform.android ||
      defaultTargetPlatform == TargetPlatform.iOS ||
      defaultTargetPlatform == TargetPlatform.macOS;

  String get _platform => kIsWeb
      ? 'web'
      : switch (defaultTargetPlatform) {
          TargetPlatform.android => 'android',
          TargetPlatform.iOS => 'ios',
          TargetPlatform.macOS => 'macos',
          _ => throw UnsupportedError('Plataforma sin FCM'),
        };
}
