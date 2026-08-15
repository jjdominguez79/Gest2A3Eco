import 'package:flutter/foundation.dart';
import 'package:firebase_core/firebase_core.dart';
import 'package:firebase_messaging/firebase_messaging.dart';

import '../api/api_client.dart';
import '../../features/auth/domain/user_profile.dart';

class NotificationsService {
  bool _initialized = false;

  Future<void> initialize(AuthSession session, ApiClient api) async {
    if (_initialized) return;
    try {
      await Firebase.initializeApp();
      final messaging = FirebaseMessaging.instance;
      await messaging.requestPermission();
      final token = await messaging.getToken();
      if (token == null) return;
      final platform = kIsWeb
          ? 'web'
          : switch (defaultTargetPlatform) {
              TargetPlatform.android => 'android',
              TargetPlatform.iOS => 'ios',
              TargetPlatform.macOS => 'macos',
              TargetPlatform.windows => 'windows',
              _ => 'web',
            };
      await api.dio.put<void>(
        '/${session.profile.type.name}/app-devices',
        data: {
          'platform': platform,
          'push_token': token,
          'device_name': '',
          'app_version': '0.1.0',
        },
      );
      _initialized = true;
    } catch (_) {
      // Firebase es opcional en desarrollo y no debe impedir usar REST/WebSocket.
    }
  }
}
