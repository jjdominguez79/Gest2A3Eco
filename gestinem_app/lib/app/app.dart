import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../core/notifications/notifications_service.dart';
import '../core/websocket/realtime_service.dart';
import '../features/auth/domain/user_profile.dart';
import '../features/auth/presentation/auth_controller.dart';
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

  @override
  void initState() {
    super.initState();
    _notifications = ref
        .read(notificationsServiceProvider)
        .events
        .listen(_handleNotification);
  }

  void _handleNotification(NotificationEvent event) {
    ref.invalidate(conversationsProvider);
    ref.invalidate(unifiedConversationProvider);
    ref.invalidate(unifiedMessagesProvider);
    if (event.conversationId.isNotEmpty) {
      ref.invalidate(messagesProvider(event.conversationId));
    }
    final threadId = event.threadId;
    if (threadId != null && threadId.isNotEmpty) {
      ref.invalidate(internalThreadsProvider);
      ref.invalidate(internalMessagesProvider(threadId));
      if (event.opened) ref.read(routerProvider).go('/internal/$threadId');
    } else if (event.opened && event.conversationId.isNotEmpty) {
      ref.read(routerProvider).go('/conversation/${event.conversationId}');
    }
  }

  void _ensureRealtime(AuthSession session) {
    final owner = '${session.profile.type.name}:${session.profile.id}';
    if (_realtimeOwner == owner) return;
    _realtimeOwner = owner;
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
    final conversationId = event['conversation_id'] as String?;
    if (conversationId != null && conversationId.isNotEmpty) {
      ref.invalidate(messagesProvider(conversationId));
    }
    final threadId = event['thread_id'] as String?;
    if (threadId != null && threadId.isNotEmpty) {
      ref.invalidate(internalThreadsProvider);
      ref.invalidate(internalMessagesProvider(threadId));
    }
  }

  @override
  void dispose() {
    _notifications?.cancel();
    _realtimeEvents?.cancel();
    _realtime?.close();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final session = ref.watch(sessionProvider).valueOrNull;
    if (session != null) {
      _ensureRealtime(session);
      unawaited(
        ref
            .read(notificationsServiceProvider)
            .initialize(session, ref.read(apiClientProvider)),
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
