import 'package:flutter/widgets.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import 'app/app.dart';
import 'core/deep_links/windows_protocol.dart';

Future<void> main() async {
  WidgetsFlutterBinding.ensureInitialized();
  await registerWindowsProtocol();
  runApp(const ProviderScope(child: GestinemApp()));
}
