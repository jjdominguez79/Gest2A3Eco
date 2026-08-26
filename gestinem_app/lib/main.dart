import 'package:flutter/widgets.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import 'app/app.dart';
import 'core/deep_links/windows_protocol.dart';
import 'core/notifications/notifications_service.dart';

Future<void> main() async {
  WidgetsFlutterBinding.ensureInitialized();
  configureFirebaseBackgroundMessaging();
  await registerWindowsProtocol();
  runApp(const ProviderScope(child: GestinemApp()));
}
