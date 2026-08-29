import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter/foundation.dart';

import '../core/notifications/notifications_service.dart';
import '../core/notifications/web_permission_state.dart';
import '../core/websocket/realtime_service.dart';
import '../features/auth/domain/user_profile.dart';
import '../features/auth/presentation/auth_controller.dart';
import '../features/empleados/presentation/empleados_screen.dart';
import '../features/documents/presentation/documents_providers.dart';
import '../features/messaging/presentation/messaging_providers.dart';
import 'router.dart';

class GestinemApp extends ConsumerStatefulWidget {
  const GestinemApp({super.key});

  @override
  ConsumerState<GestinemApp> createState() => _GestinemAppState();
}

class _GestinemAppState extends ConsumerState<GestinemApp> {
  StreamSubscription<NotificationEvent>? _notifications;
  StreamSubscription<Map<String, dynamic>>? _realtimeEvents;
  RealtimeService? _realtime;
  String? _realtimeOwner;
  Timer? _presenceRefresh;
  String? _lastOpenedNotification;

  @override
  void initState() {
    super.initState();
    _notifications = ref
        .read(notificationsServiceProvider)
        .events
        .listen(_handleNotification);
  }

  void _handleNotification(NotificationEvent event) {
    final documentId = event.documentId;
    if (documentId != null && documentId.isNotEmpty) {
      ref.invalidate(documentsProvider);
      ref.invalidate(documentDetailProvider(documentId));
      if (event.opened && ref.read(sessionProvider).valueOrNull != null) {
        final target = 'document:$documentId';
        if (_lastOpenedNotification == target) return;
        _lastOpenedNotification = target;
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
      final target = threadId != null && threadId.isNotEmpty
          ? 'internal:$threadId'
          : 'conversation:${event.conversationId}';
      if (_lastOpenedNotification == target) return;
      if (ref.read(sessionProvider).valueOrNull == null) return;
      _lastOpenedNotification = target;
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
    ref.invalidate(conversationsProvider);
    ref.invalidate(unifiedConversationProvider);
    ref.invalidate(unifiedMessagesProvider);
    if (event['type'] == 'presence.updated') {
      ref.invalidate(internalThreadsProvider);
      ref.invalidate(empleadosProvider);
    }
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
    final route = threadId != null && threadId.isNotEmpty
        ? '/internal/$threadId'
        : (conversationId != null && conversationId.isNotEmpty
              ? '/conversation/$conversationId'
              : '/');
    unawaited(
      ref
          .read(notificationsServiceProvider)
          .showDesktop(
            title: authorName.isEmpty
                ? 'Nuevo mensaje en Gestinem'
                : 'Nuevo mensaje de $authorName',
            body: preview.isEmpty ? 'Tienes un nuevo mensaje' : preview,
            onClick: () => ref.read(routerProvider).go(route),
          ),
    );
  }

  @override
  void dispose() {
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

    if (service.permissionState == NotificationPermissionState.authorized) {
      ref.read(webNotifPermissionProvider.notifier).markGranted();
    }
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
