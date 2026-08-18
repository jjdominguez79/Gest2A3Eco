import 'dart:async';

import 'package:flutter/foundation.dart';
import 'package:firebase_core/firebase_core.dart';
import 'package:firebase_messaging/firebase_messaging.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../api/api_client.dart';
import '../../features/auth/domain/user_profile.dart';

final notificationsServiceProvider =
    Provider<NotificationsService>((ref) => NotificationsService());

class NotificationsService {
  String? _owner;
  String? _deviceId;
  StreamSubscription<String>? _tokenRefresh;

  Future<void> initialize(AuthSession session, ApiClient api) async {
    if (!_supported || _owner == _ownerFor(session)) return;
    try {
      if (Firebase.apps.isEmpty) await Firebase.initializeApp();
      final messaging = FirebaseMessaging.instance;
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
      debugPrint('No se pudieron activar las notificaciones: $error\n$stackTrace');
    }
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
    final response = await api.dio.put<Map<String, dynamic>>(
      '/${session.profile.type.name}/app-devices',
      data: {
        'platform': _platform,
        'push_token': token,
        'device_name': '',
        'app_version': '0.1.0',
      },
    );
    _deviceId = response.data?['id'] as String?;
  }

  String _ownerFor(AuthSession session) =>
      '${session.profile.type.name}:${session.profile.id}';

  bool get _supported => kIsWeb ||
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
