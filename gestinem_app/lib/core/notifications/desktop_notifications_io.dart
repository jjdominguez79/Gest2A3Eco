import 'dart:io';

import 'package:local_notifier/local_notifier.dart';

class DesktopNotifications {
  bool _initialized = false;

  bool get supported => Platform.isWindows;

  Future<void> initialize() async {
    if (!supported || _initialized) return;
    await localNotifier.setup(
      appName: 'Gestinem',
      shortcutPolicy: ShortcutPolicy.requireCreate,
    );
    _initialized = true;
  }

  Future<void> show({
    required String title,
    required String body,
    required void Function() onClick,
  }) async {
    if (!supported) return;
    await initialize();
    final notification = LocalNotification(title: title, body: body);
    notification.onClick = onClick;
    await notification.show();
  }
}
