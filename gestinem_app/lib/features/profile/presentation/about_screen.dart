import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:in_app_update/in_app_update.dart';
import 'package:package_info_plus/package_info_plus.dart';

import '../../../core/config/app_config.dart';
import '../../messaging/presentation/messaging_providers.dart';

class AboutScreen extends ConsumerStatefulWidget {
  const AboutScreen({super.key});

  @override
  ConsumerState<AboutScreen> createState() => _AboutScreenState();
}

class _AboutScreenState extends ConsumerState<AboutScreen> {
  late Future<_VersionInformation> _information;

  @override
  void initState() {
    super.initState();
    _information = _loadInformation();
  }

  Future<_VersionInformation> _loadInformation() async {
    final package = await PackageInfo.fromPlatform();
    AppUpdateInfo? playUpdate;
    if (!kIsWeb && defaultTargetPlatform == TargetPlatform.android) {
      try {
        playUpdate = await InAppUpdate.checkForUpdate();
      } catch (_) {
        // Solo funciona con instalaciones realizadas desde Google Play.
      }
    }
    try {
      final remote = await ref
          .read(messagingRepositoryProvider)
          .latestAppVersion(_platformName);
      return _VersionInformation(
        package: package,
        remote: remote,
        playUpdate: playUpdate,
      );
    } catch (_) {
      return _VersionInformation(package: package, playUpdate: playUpdate);
    }
  }

  void _refresh() {
    setState(() => _information = _loadInformation());
  }

  @override
  Widget build(BuildContext context) => Scaffold(
    appBar: AppBar(
      leading: IconButton(
        onPressed: () => context.go('/'),
        icon: const Icon(Icons.arrow_back),
      ),
      title: const Text('Acerca de Gestinem'),
      actions: [
        IconButton(
          tooltip: 'Comprobar actualizaciones',
          onPressed: _refresh,
          icon: const Icon(Icons.refresh),
        ),
      ],
    ),
    body: FutureBuilder<_VersionInformation>(
      future: _information,
      builder: (context, snapshot) {
        if (!snapshot.hasData) {
          return const Center(child: CircularProgressIndicator());
        }
        final information = snapshot.requireData;
        final status = information.status;
        return Center(
          child: ConstrainedBox(
            constraints: const BoxConstraints(maxWidth: 620),
            child: ListView(
              padding: EdgeInsets.fromLTRB(
                24,
                24,
                24,
                24 + MediaQuery.viewPaddingOf(context).bottom,
              ),
              children: [
                Center(
                  child: Image.asset(
                    'assets/images/logo_new.png',
                    width: 82,
                    height: 82,
                  ),
                ),
                const SizedBox(height: 12),
                Text(
                  'Gestinem',
                  textAlign: TextAlign.center,
                  style: Theme.of(context).textTheme.headlineSmall,
                ),
                const SizedBox(height: 24),
                Card(
                  child: Column(
                    children: [
                      ListTile(
                        leading: Icon(
                          status.icon,
                          color: status.color(context),
                        ),
                        title: Text(status.title),
                        subtitle: Text(status.description),
                      ),
                      const Divider(height: 1),
                      ListTile(
                        leading: const Icon(Icons.info_outline),
                        title: const Text('Versión Instalada'),
                        subtitle: Text(
                          '${information.package.version} '
                          '(compilación ${information.package.buildNumber})',
                        ),
                      ),
                      if (information.playAvailableBuild != null)
                        ListTile(
                          leading: const Icon(Icons.shop_outlined),
                          title: const Text('Actualización en Google Play'),
                          subtitle: Text(
                            'Compilación ${information.playAvailableBuild}',
                          ),
                        )
                      else if (_platformName != 'android' &&
                          information.remote?['enabled'] == true)
                        ListTile(
                          leading: const Icon(Icons.cloud_outlined),
                          title: const Text('Última versión disponible'),
                          subtitle: Text(
                            '${information.remote!['latest_version']} '
                            '(compilación ${information.remote!['latest_build']})',
                          ),
                        ),
                      ListTile(
                        leading: const Icon(Icons.devices_outlined),
                        title: const Text('Plataforma'),
                        subtitle: Text(_platformName),
                      ),
                      ListTile(
                        leading: const Icon(Icons.settings_outlined),
                        title: const Text('Entorno'),
                        subtitle: Text(appConfig.environment),
                      ),
                    ],
                  ),
                ),
                const SizedBox(height: 16),
                const Text(
                  'Cuando exista una nueva versión, esta pantalla lo indicará. '
                  'En Android, Google Play la detectará automáticamente al '
                  'abrir la aplicación. En Windows, el instalador debe '
                  'solicitarse al despacho.',
                  textAlign: TextAlign.center,
                ),
              ],
            ),
          ),
        );
      },
    ),
  );
}

String get _platformName => kIsWeb
    ? 'web'
    : switch (defaultTargetPlatform) {
        TargetPlatform.android => 'android',
        TargetPlatform.iOS => 'ios',
        TargetPlatform.windows => 'windows',
        TargetPlatform.macOS => 'macos',
        TargetPlatform.linux => 'linux',
        TargetPlatform.fuchsia => 'fuchsia',
      };

class _VersionInformation {
  const _VersionInformation({
    required this.package,
    this.remote,
    this.playUpdate,
  });

  final PackageInfo package;
  final Map<String, dynamic>? remote;
  final AppUpdateInfo? playUpdate;

  int? get playAvailableBuild {
    final update = playUpdate;
    if (update == null || !_playUpdateAvailable(update)) return null;
    return update.availableVersionCode;
  }

  _VersionStatus get status {
    final localBuild = int.tryParse(package.buildNumber) ?? 0;
    if (_platformName == 'android') {
      final updateEnabled = remote?['enabled'] == true;
      final minimumBuild = remote?['minimum_build'] as int? ?? 0;
      if (updateEnabled && localBuild < minimumBuild) {
        return _VersionStatus.required;
      }
      if (playUpdate == null) return _VersionStatus.unknown;
      return _playUpdateAvailable(playUpdate!)
          ? _VersionStatus.available
          : _VersionStatus.current;
    }
    if (remote == null) return _VersionStatus.unknown;
    if (remote!['enabled'] != true) return _VersionStatus.current;
    final latestBuild = remote!['latest_build'] as int? ?? 0;
    final minimumBuild = remote!['minimum_build'] as int? ?? 0;
    if (localBuild < minimumBuild) return _VersionStatus.required;
    if (localBuild < latestBuild) return _VersionStatus.available;
    return _VersionStatus.current;
  }
}

bool _playUpdateAvailable(AppUpdateInfo update) =>
    update.updateAvailability == UpdateAvailability.updateAvailable ||
    update.updateAvailability ==
        UpdateAvailability.developerTriggeredUpdateInProgress;

enum _VersionStatus {
  current,
  available,
  required,
  unknown;

  String get title => switch (this) {
    current => 'Aplicación actualizada',
    available => 'Hay una versión más reciente',
    required => 'Actualización necesaria',
    unknown => 'No se pudo comprobar la última versión',
  };

  String get description => switch (this) {
    current => 'Estás utilizando la última versión disponible.',
    available =>
      'Actualiza cuando te resulte posible para recibir las mejoras.',
    required => 'Esta versión es demasiado antigua y debe actualizarse.',
    unknown =>
      'La versión instalada se muestra debajo. Inténtalo de nuevo más tarde.',
  };

  IconData get icon => switch (this) {
    current => Icons.verified_outlined,
    available => Icons.system_update_outlined,
    required => Icons.warning_amber_outlined,
    unknown => Icons.cloud_off_outlined,
  };

  Color color(BuildContext context) => switch (this) {
    current => Colors.green,
    available => Colors.orange,
    required => Theme.of(context).colorScheme.error,
    unknown => Theme.of(context).colorScheme.onSurfaceVariant,
  };
}
