import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../features/auth/presentation/auth_controller.dart';
import 'web_permission_state.dart';

/// Banner de permisos de notificacion, exclusivo para Flutter Web.
///
/// En Android y Windows este widget no renderiza nada.
/// No abre el dialogo del navegador automaticamente; el usuario debe
/// pulsar el boton "Activar notificaciones".
class WebNotificationPermissionBanner extends ConsumerWidget {
  const WebNotificationPermissionBanner({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    if (!kIsWeb) return const SizedBox.shrink();

    final permission = ref.watch(webNotifPermissionProvider);

    return switch (permission) {
      NotificationPermissionState.authorized => const SizedBox.shrink(),
      NotificationPermissionState.available => _ActivateBanner(ref: ref),
      NotificationPermissionState.pending => _StatusBanner(
        icon: Icons.hourglass_top,
        message: 'Activando notificaciones\u2026',
        color: Colors.blue.shade50,
      ),
      NotificationPermissionState.denied => _DeniedBanner(),
      NotificationPermissionState.configError => _StatusBanner(
        icon: Icons.warning_amber_rounded,
        message:
            'Notificaciones no disponibles: configuracion de Firebase incompleta.',
        color: Colors.orange.shade50,
      ),
    };
  }
}

class _ActivateBanner extends ConsumerWidget {
  const _ActivateBanner({required this.ref});

  final WidgetRef ref;

  @override
  Widget build(BuildContext context, WidgetRef r) {
    final session = r.read(sessionProvider).valueOrNull;
    final api = r.read(apiClientProvider);

    return _BannerShell(
      color: Colors.blue.shade50,
      icon: Icons.notifications_none,
      message:
          'Activa las notificaciones para recibir avisos de nuevos mensajes.',
      action: TextButton(
        onPressed: session == null
            ? null
            : () => r
                  .read(webNotifPermissionProvider.notifier)
                  .activate(session, api),
        child: const Text('Activar notificaciones'),
      ),
    );
  }
}

class _DeniedBanner extends StatelessWidget {
  @override
  Widget build(BuildContext context) {
    return _BannerShell(
      color: Colors.red.shade50,
      icon: Icons.notifications_off,
      message:
          'Notificaciones bloqueadas. Para habilitarlas: '
          'haz clic en el icono de candado junto a la URL \u2192 Notificaciones \u2192 Permitir.',
      action: null,
    );
  }
}

class _StatusBanner extends StatelessWidget {
  const _StatusBanner({
    required this.icon,
    required this.message,
    required this.color,
  });

  final IconData icon;
  final String message;
  final Color color;

  @override
  Widget build(BuildContext context) {
    return _BannerShell(
      color: color,
      icon: icon,
      message: message,
      action: null,
    );
  }
}

class _BannerShell extends StatelessWidget {
  const _BannerShell({
    required this.color,
    required this.icon,
    required this.message,
    required this.action,
  });

  final Color color;
  final IconData icon;
  final String message;
  final Widget? action;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return Material(
      color: color,
      child: Padding(
        padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 10),
        child: Row(
          children: [
            Icon(icon, size: 20, color: theme.colorScheme.primary),
            const SizedBox(width: 12),
            Expanded(child: Text(message, style: theme.textTheme.bodySmall)),
            if (action != null) ...[const SizedBox(width: 8), action!],
          ],
        ),
      ),
    );
  }
}
