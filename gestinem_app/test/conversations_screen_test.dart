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
  testWidgets('lista de chats muestra canal, empresa y no leidos', (tester) async {
    final row = Conversation(
      id: 'c1', companyCode: 'E00001', companyName: 'Empresa Uno',
      kind: 'fiscal', state: 'pendiente', unreadCount: 3,
      updatedAt: DateTime(2026, 8, 15),
    );
    await tester.pumpWidget(ProviderScope(
      overrides: [
        sessionProvider.overrideWith((ref) => FakeSessionController(ref)),
        conversationsProvider.overrideWith((ref) async => [row]),
        realtimeServiceProvider.overrideWithValue(_FakeRealtime()),
        notificationsServiceProvider.overrideWithValue(_FakeNotifications()),
      ],
      child: const MaterialApp(home: ConversationsScreen()),
    ));
    await tester.pump();

    expect(find.byKey(const Key('conversation-list')), findsOneWidget);
    expect(find.text('Empresa Uno'), findsOneWidget);
    expect(find.textContaining('E00001'), findsOneWidget);
    expect(find.text('3'), findsOneWidget);
  });
}
