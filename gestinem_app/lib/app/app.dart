import 'dart:async';

import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:in_app_update/in_app_update.dart';
import 'package:package_info_plus/package_info_plus.dart';
import 'package:url_launcher/url_launcher.dart';

import '../core/notifications/notifications_service.dart';
import '../core/notifications/web_permission_state.dart';
import '../core/websocket/realtime_service.dart';
import '../features/app_update/domain/app_update_policy.dart';
import '../features/auth/domain/user_profile.dart';
import '../features/auth/presentation/auth_controller.dart';
import '../features/empleados/presentation/empleados_screen.dart';
import '../features/documents/presentation/documents_providers.dart';
import '../features/subvenciones/presentation/subvenciones_providers.dart';
import '../features/messaging/presentation/messaging_providers.dart';
import 'router.dart';

class GestinemApp extends ConsumerStatefulWidget {
  const GestinemApp({super.key});

  @override
  ConsumerState<GestinemApp> createState() => _GestinemAppState();
}

class _GestinemAppState extends ConsumerState<GestinemApp>
    with WidgetsBindingObserver {
  static final Uri _androidStoreUrl = Uri.parse(
    'https://play.google.com/store/apps/details?id=es.gestinem.app',
  );

  StreamSubscription<NotificationEvent>? _notifications;
  StreamSubscription<Map<String, dynamic>>? _realtimeEvents;
  RealtimeService? _realtime;
  String? _realtimeOwner;
  Timer? _presenceRefresh;
  final NotificationOpenGuard _notificationOpenGuard = NotificationOpenGuard();
  bool _checkingUpdate = false;
  bool _updateDialogVisible = false;
  int? _dismissedOptionalBuild;
  DateTime? _lastUpdateCheck;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addObserver(this);
    _notifications = ref
        .read(notificationsServiceProvider)
        .events
        .listen(_handleNotification);
    WidgetsBinding.instance.addPostFrameCallback(
      (_) => unawaited(_checkAppUpdate(force: true)),
    );
  }

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    if (state == AppLifecycleState.resumed) {
      unawaited(_checkAppUpdate());
    }
  }

  String? get _updatePlatform {
    if (kIsWeb) return null;
    return switch (defaultTargetPlatform) {
      TargetPlatform.android => 'android',
      TargetPlatform.iOS => 'ios',
      _ => null,
    };
  }

  Future<void> _checkAppUpdate({bool force = false}) async {
    final platform = _updatePlatform;
    if (platform == null || _checkingUpdate || _updateDialogVisible) return;
    final now = DateTime.now();
    if (!force &&
        _lastUpdateCheck != null &&
        now.difference(_lastUpdateCheck!) < const Duration(minutes: 15)) {
      return;
    }
    _checkingUpdate = true;
    _lastUpdateCheck = now;
    try {
      if (platform == 'android') {
        await _checkAndroidPlayUpdate();
      } else {
        await _checkPolicyUpdate(platform);
      }
    } catch (_) {
      // Una comprobacion fallida nunca debe impedir abrir la aplicacion.
    } finally {
      _checkingUpdate = false;
    }
  }

  Future<AppUpdatePolicy?> _loadUpdatePolicy(String platform) async {
    try {
      final remote = await ref
          .read(messagingRepositoryProvider)
          .latestAppVersion(platform);
      return AppUpdatePolicy.fromJson(remote);
    } catch (_) {
      // Google Play puede seguir comprobando actualizaciones aunque el backend
      // no este disponible. La politica remota solo decide si son obligatorias.
      return null;
    }
  }

  Future<void> _checkAndroidPlayUpdate() async {
    final package = await PackageInfo.fromPlatform();
    final installedBuild = int.tryParse(package.buildNumber) ?? 0;
    final policy = await _loadUpdatePolicy('android');
    final mandatory = policy?.requiresMinimumBuild(installedBuild) ?? false;
    final storeUrl = policy?.storeUrl ?? _androidStoreUrl;

    AppUpdateInfo update;
    try {
      update = await InAppUpdate.checkForUpdate();
    } catch (_) {
      if (mandatory && mounted) {
        await _showUpdateDialog(mandatory: true, storeUrl: storeUrl);
      }
      return;
    }

    if (!mounted) return;
    if (update.installStatus == InstallStatus.downloaded) {
      try {
        await InAppUpdate.completeFlexibleUpdate();
      } catch (_) {
        await _showUpdateDialog(
          mandatory: mandatory,
          storeUrl: storeUrl,
          availableBuild: update.availableVersionCode,
        );
      }
      return;
    }

    final updateAvailable =
        update.updateAvailability == UpdateAvailability.updateAvailable ||
        update.updateAvailability ==
            UpdateAvailability.developerTriggeredUpdateInProgress;
    if (!updateAvailable) {
      if (mandatory) {
        await _showUpdateDialog(mandatory: true, storeUrl: storeUrl);
      }
      return;
    }

    final immediateInProgress =
        update.updateAvailability ==
        UpdateAvailability.developerTriggeredUpdateInProgress;
    if ((mandatory || immediateInProgress) && update.immediateUpdateAllowed) {
      try {
        final result = await InAppUpdate.performImmediateUpdate();
        if (result == AppUpdateResult.success || !mounted) return;
      } catch (_) {
        if (!mounted) return;
      }
      await _showUpdateDialog(
        mandatory: mandatory || immediateInProgress,
        storeUrl: storeUrl,
        availableBuild: update.availableVersionCode,
      );
      return;
    }

    if (!mandatory && update.flexibleUpdateAllowed) {
      try {
        final result = await InAppUpdate.startFlexibleUpdate();
        if (result == AppUpdateResult.success) {
          await InAppUpdate.completeFlexibleUpdate();
        } else if (result == AppUpdateResult.inAppUpdateFailed && mounted) {
          await _showUpdateDialog(
            mandatory: false,
            storeUrl: storeUrl,
            availableBuild: update.availableVersionCode,
          );
        }
      } catch (_) {
        if (mounted) {
          await _showUpdateDialog(
            mandatory: false,
            storeUrl: storeUrl,
            availableBuild: update.availableVersionCode,
          );
        }
      }
      return;
    }

    await _showUpdateDialog(
      mandatory: mandatory,
      storeUrl: storeUrl,
      availableBuild: update.availableVersionCode,
    );
  }

  Future<void> _checkPolicyUpdate(String platform) async {
    final policy = await _loadUpdatePolicy(platform);
    if (policy == null) return;
    final package = await PackageInfo.fromPlatform();
    final installedBuild = int.tryParse(package.buildNumber) ?? 0;
    if (!mounted) return;
    final requirement = policy.requirementFor(installedBuild);
    if (requirement == AppUpdateRequirement.disabled ||
        requirement == AppUpdateRequirement.current ||
        (requirement == AppUpdateRequirement.optional &&
            _dismissedOptionalBuild == policy.latestBuild)) {
      return;
    }
    final mandatory = requirement == AppUpdateRequirement.mandatory;
    await _showUpdateDialog(
      mandatory: mandatory,
      storeUrl: policy.storeUrl!,
      latestVersion: policy.latestVersion,
      dismissedBuild: policy.latestBuild,
    );
  }

  Future<void> _showUpdateDialog({
    required bool mandatory,
    required Uri storeUrl,
    String? latestVersion,
    int? availableBuild,
    int? dismissedBuild,
  }) async {
    if (_updateDialogVisible) return;
    final navigator = ref.read(rootNavigatorKeyProvider).currentState;
    if (navigator == null || !navigator.mounted) return;
    final versionDescription = latestVersion != null && latestVersion.isNotEmpty
        ? 'la versión $latestVersion'
        : availableBuild != null
        ? 'la compilación $availableBuild'
        : 'la actualización disponible';
    _updateDialogVisible = true;
    await showDialog<void>(
      context: navigator.context,
      barrierDismissible: !mandatory,
      builder: (dialogContext) => PopScope(
        canPop: !mandatory,
        child: AlertDialog(
          icon: Icon(
            mandatory ? Icons.warning_amber_rounded : Icons.system_update,
          ),
          title: Text(
            mandatory ? 'Actualización necesaria' : 'Actualización disponible',
          ),
          content: Text(
            mandatory
                ? 'Debes instalar $versionDescription para '
                      'seguir utilizando Gestinem Chat.'
                : 'Ya está disponible $versionDescription de '
                      'Gestinem Chat. Te recomendamos actualizarla.',
          ),
          actions: [
            if (!mandatory)
              TextButton(
                onPressed: () {
                  _dismissedOptionalBuild = dismissedBuild ?? availableBuild;
                  Navigator.of(dialogContext).pop();
                },
                child: const Text('Más tarde'),
              ),
            FilledButton.icon(
              onPressed: () {
                if (!mandatory) Navigator.of(dialogContext).pop();
                unawaited(_openStore(storeUrl));
              },
              icon: const Icon(Icons.open_in_new),
              label: const Text('Actualizar ahora'),
            ),
          ],
        ),
      ),
    );
    _updateDialogVisible = false;
  }

  Future<void> _openStore(Uri storeUrl) async {
    await launchUrl(storeUrl, mode: LaunchMode.externalApplication);
  }

  void _handleNotification(NotificationEvent event) {
    final subvencionId = event.subvencionId;
    if (subvencionId != null && subvencionId.isNotEmpty) {
      ref.invalidate(subvencionesProvider);
      ref.invalidate(subvencionProvider(subvencionId));
      if (event.opened && ref.read(sessionProvider).valueOrNull != null) {
        if (!_notificationOpenGuard.shouldHandle(event)) return;
        ref.read(routerProvider).go('/subvenciones/$subvencionId');
      }
      return;
    }
    final documentId = event.documentId;
    if (documentId != null && documentId.isNotEmpty) {
      ref.invalidate(documentsProvider);
      ref.invalidate(documentDetailProvider(documentId));
      if (event.opened && ref.read(sessionProvider).valueOrNull != null) {
        if (!_notificationOpenGuard.shouldHandle(event)) return;
        ref.read(routerProvider).go('/documents/$documentId');
      }
      return;
    }
    ref.invalidate(conversationsProvider);
    ref.invalidate(unifiedConversationProvider);
    ref.invalidate(unifiedMessagesProvider);
    if (event.conversationId.isNotEmpty) {
      ref.invalidate(messagesProvider(event.conversationId));
    }
    final threadId = event.threadId;
    if (event.opened) {
      if (ref.read(sessionProvider).valueOrNull == null) return;
      if (!_notificationOpenGuard.shouldHandle(event)) return;
    }
    if (threadId != null && threadId.isNotEmpty) {
      ref.invalidate(internalThreadsProvider);
      ref.invalidate(internalMessagesProvider(threadId));
      if (event.opened) ref.read(routerProvider).go('/internal/$threadId');
    } else if (event.opened && event.conversationId.isNotEmpty) {
      ref.read(routerProvider).go('/conversation/${event.conversationId}');
    }
  }

  void _consumePendingNotification() {
    final event = ref
        .read(notificationsServiceProvider)
        .takePendingOpenedEvent();
    if (event != null) _handleNotification(event);
  }

  void _ensureRealtime(AuthSession session) {
    final owner = '${session.profile.type.name}:${session.profile.id}';
    if (_realtimeOwner == owner) return;
    _realtimeOwner = owner;
    if (session.profile.type == UserType.staff) {
      _presenceRefresh ??= Timer.periodic(const Duration(seconds: 30), (_) {
        ref.invalidate(internalThreadsProvider);
        ref.invalidate(empleadosProvider);
      });
    }
    unawaited(_replaceRealtime(owner, session));
  }

  Future<void> _replaceRealtime(String owner, AuthSession session) async {
    await _realtimeEvents?.cancel();
    await _realtime?.close();
    if (_realtimeOwner != owner) return;
    ref.invalidate(realtimeServiceProvider);
    final realtime = ref.read(realtimeServiceProvider);
    _realtime = realtime;
    _realtimeEvents = realtime.events.listen(_handleRealtime);
    unawaited(realtime.connect(session, ref.read(apiClientProvider)));
  }

  void _stopRealtime() {
    if (_realtimeOwner == null) return;
    _realtimeOwner = null;
    _presenceRefresh?.cancel();
    _presenceRefresh = null;
    final events = _realtimeEvents;
    final realtime = _realtime;
    _realtimeEvents = null;
    _realtime = null;
    unawaited(events?.cancel());
    unawaited(realtime?.close());
  }

  void _handleRealtime(Map<String, dynamic> event) {
    if (event['type'] == 'ping') return;
    if (event['type'] == 'message.states_updated') {
      ref.invalidate(conversationsProvider);
      ref.invalidate(unifiedConversationProvider);
      ref.invalidate(unifiedMessagesProvider);
      ref.invalidate(messagesProvider);
      ref.invalidate(internalThreadsProvider);
      ref.invalidate(internalMessagesProvider);
      return;
    }
    if (event['type'] == 'presence.updated' ||
        event['type'] == 'connected' ||
        event['type'] == 'disconnected') {
      ref.invalidate(internalThreadsProvider);
      ref.invalidate(empleadosProvider);
      if (event['type'] != 'connected') return;
      // Al reconectar, refrescar tambien los chats abiertos por si alguna
      // confirmacion de lectura llego mientras el socket estaba desconectado.
      ref.invalidate(messagesProvider);
      ref.invalidate(internalMessagesProvider);
    }
    if (event['type'] == 'document.published') {
      final session = ref.read(sessionProvider).valueOrNull;
      if (session?.profile.type != UserType.client) return;
      final documentId = event['document_id']?.toString() ?? '';
      if (documentId.isEmpty) return;
      ref.invalidate(documentsProvider);
      ref.invalidate(documentDetailProvider(documentId));
      unawaited(
        ref
            .read(notificationsServiceProvider)
            .showDesktop(
              title: event['title']?.toString() ?? 'Nuevo documento disponible',
              body: event['body']?.toString() ?? 'Tienes un nuevo documento',
              targetType: 'document',
              targetId: documentId,
            ),
      );
      return;
    }
    ref.invalidate(conversationsProvider);
    ref.invalidate(unifiedConversationProvider);
    ref.invalidate(unifiedMessagesProvider);
    final conversationId = event['conversation_id'] as String?;
    if (conversationId != null && conversationId.isNotEmpty) {
      ref.invalidate(messagesProvider(conversationId));
    }
    final threadId = event['thread_id'] as String?;
    if (threadId != null && threadId.isNotEmpty) {
      ref.invalidate(internalThreadsProvider);
      ref.invalidate(internalMessagesProvider(threadId));
    }
    _showWindowsNotification(event, conversationId, threadId);
  }

  void _showWindowsNotification(
    Map<String, dynamic> event,
    String? conversationId,
    String? threadId,
  ) {
    if (event['type'] != 'message.created') return;
    final session = ref.read(sessionProvider).valueOrNull;
    if (session == null) return;
    final authorType = event['author_type']?.toString() ?? '';
    final authorId = event['author_id']?.toString() ?? '';
    if (authorType == session.profile.type.name &&
        authorId == session.profile.id) {
      return;
    }
    final authorName = event['author_name']?.toString().trim() ?? '';
    final preview = event['preview']?.toString().trim() ?? '';
    final mentionedIds =
        (event['mentioned_staff_ids'] as List<dynamic>? ?? const [])
            .map((value) => value.toString())
            .toSet();
    final mentioned = mentionedIds.contains(session.profile.id);
    unawaited(
      ref
          .read(notificationsServiceProvider)
          .showDesktop(
            title: mentioned
                ? (authorName.isEmpty
                      ? 'Te han mencionado en Gestinem'
                      : '$authorName te ha mencionado')
                : (authorName.isEmpty
                      ? 'Nuevo mensaje en Gestinem'
                      : 'Nuevo mensaje de $authorName'),
            body: mentioned
                ? (preview.isEmpty
                      ? 'Te han etiquetado en un mensaje del grupo'
                      : preview)
                : (preview.isEmpty ? 'Tienes un nuevo mensaje' : preview),
            targetType: threadId != null && threadId.isNotEmpty
                ? 'internal_thread'
                : 'conversation',
            targetId: threadId != null && threadId.isNotEmpty
                ? threadId
                : conversationId ?? '',
            notificationId: event['message_id']?.toString(),
          ),
    );
  }

  @override
  void dispose() {
    WidgetsBinding.instance.removeObserver(this);
    _notifications?.cancel();
    _realtimeEvents?.cancel();
    _realtime?.close();
    _presenceRefresh?.cancel();
    super.dispose();
  }

  Future<void> _initializeNotifications(AuthSession session) async {
    final service = ref.read(notificationsServiceProvider);
    final api = ref.read(apiClientProvider);

    await service.initialize(session, api);

    if (!mounted || !kIsWeb) return;

    ref
        .read(webNotifPermissionProvider.notifier)
        .syncRegistration(service.permissionState);
  }

  @override
  Widget build(BuildContext context) {
    final session = ref.watch(sessionProvider).valueOrNull;
    if (session != null) {
      _ensureRealtime(session);
      unawaited(_initializeNotifications(session));
      WidgetsBinding.instance.addPostFrameCallback(
        (_) => _consumePendingNotification(),
      );
    } else {
      _stopRealtime();
    }
    return MaterialApp.router(
      title: 'Gestinem',
      debugShowCheckedModeBanner: false,
      routerConfig: ref.watch(routerProvider),
      theme: ThemeData(
        colorScheme: ColorScheme.fromSeed(
          seedColor: const Color(0xFF004B76),
          primary: const Color(0xFF004B76),
          secondary: const Color(0xFF1B91CF),
          surface: const Color(0xFFF8FAFC),
        ),
        scaffoldBackgroundColor: const Color(0xFFF2F6F8),
        useMaterial3: true,
        inputDecorationTheme: const InputDecorationTheme(
          border: OutlineInputBorder(),
          filled: true,
          fillColor: Colors.white,
        ),
        cardTheme: const CardThemeData(elevation: 0, margin: EdgeInsets.zero),
      ),
    );
  }
}
