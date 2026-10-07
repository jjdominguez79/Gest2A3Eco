import 'package:flutter/foundation.dart';
import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

final windowsTaskbarBadgeProvider = Provider<WindowsTaskbarBadge>(
  (_) => WindowsTaskbarBadge(),
);

/// Sincroniza el numero de mensajes pendientes con el icono de Windows.
class WindowsTaskbarBadge {
  WindowsTaskbarBadge({MethodChannel? channel})
    : _channel = channel ?? const MethodChannel(_channelName);

  static const _channelName = 'es.gestinem.app/taskbar_badge';
  final MethodChannel _channel;

  bool get supported =>
      !kIsWeb && defaultTargetPlatform == TargetPlatform.windows;

  Future<void> setCount(int count) async {
    if (!supported) return;
    try {
      await _channel.invokeMethod<void>('setBadge', count.clamp(0, 999999));
    } on PlatformException catch (error, stackTrace) {
      debugPrint(
        'No se pudo actualizar el contador de la barra de tareas: '
        '$error\n$stackTrace',
      );
    } on MissingPluginException {
      // Permite ejecutar tests o builds antiguos sin el canal nativo nuevo.
    }
  }
}
