import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:gestinem/features/auth/presentation/auth_controller.dart';
import 'package:gestinem/features/messaging/domain/conversation.dart';
import 'package:gestinem/features/messaging/presentation/conversations_screen.dart';
import 'package:gestinem/features/messaging/presentation/messaging_providers.dart';
import 'package:gestinem/core/api/api_client.dart';
import 'package:gestinem/core/notifications/notifications_service.dart';
import 'package:gestinem/core/websocket/realtime_service.dart';
import 'package:gestinem/features/auth/domain/user_profile.dart';

import 'test_helpers.dart';

class _FakeRealtime extends RealtimeService {
  @override
  Future<void> connect(AuthSession session, ApiClient api) async {}
}

class _FakeNotifications extends NotificationsService {
  @override
  Future<void> initialize(AuthSession session, ApiClient api) async {}
}

void main() {
  testWidgets('cliente ve tile unificado "Gestinem"', (tester) async {
    // Para clientes, la pantalla muestra la vista unificada con un tile "Gestinem"
    final meta = {
      'unread_count': 3,
      'channel_ids': {'fiscal': 'c1'},
      'last_message': {'body': 'Mensaje de prueba', 'deleted': false},
    };
    await tester.pumpWidget(ProviderScope(
      overrides: [
        sessionProvider.overrideWith((ref) => FakeSessionController(ref)),
        conversationsProvider.overrideWith((ref) async => []),
        unifiedConversationProvider.overrideWith((ref) async => meta),
        realtimeServiceProvider.overrideWithValue(_FakeRealtime()),
        notificationsServiceProvider.overrideWithValue(_FakeNotifications()),
      ],
      child: const MaterialApp(home: ConversationsScreen()),
    ));
    await tester.pump();
    await tester.pump(); // segundo pump para el FutureProvider

    expect(find.byKey(const Key('unified-conversation-tile')), findsOneWidget);
    // "Gestinem" aparece en el AppBar y en el tile
    expect(find.text('Gestinem'), findsAtLeastNWidgets(1));
    expect(find.text('3'), findsOneWidget);
  });

  testWidgets('staff ve lista agrupada por cliente', (tester) async {
    const staffProfile = UserProfile(
      id: 'staff-1',
      name: 'Gestor',
      email: 'gestor@gestinem.es',
      type: UserType.staff,
      staffRole: StaffRole.admin,
    );
    const staffSession = AuthSession(token: 'staff-token', profile: staffProfile);

    final row = Conversation(
      id: 'c1', companyCode: 'E00001', companyName: 'Empresa Uno',
      kind: 'fiscal', state: 'pendiente', unreadCount: 3,
      updatedAt: DateTime(2026, 8, 15),
    );
    await tester.pumpWidget(ProviderScope(
      overrides: [
        sessionProvider.overrideWith((ref) => FakeSessionController(ref, staffSession)),
        conversationsProvider.overrideWith((ref) async => [row]),
        realtimeServiceProvider.overrideWithValue(_FakeRealtime()),
        notificationsServiceProvider.overrideWithValue(_FakeNotifications()),
      ],
      child: const MaterialApp(home: ConversationsScreen()),
    ));
    await tester.pump();
    await tester.pump();

    expect(find.byKey(const Key('conversation-list')), findsOneWidget);
    expect(find.text('Empresa Uno'), findsOneWidget);
    expect(find.textContaining('E00001'), findsOneWidget);
    expect(find.text('3'), findsOneWidget);
  });
}
