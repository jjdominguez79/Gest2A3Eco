import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:gestinem/core/sharing/android_share_receiver.dart';
import 'package:gestinem/features/auth/presentation/auth_controller.dart';
import 'package:gestinem/features/messaging/domain/conversation.dart';
import 'package:gestinem/features/messaging/presentation/messaging_providers.dart';
import 'package:gestinem/features/messaging/presentation/share_target_sheet.dart';

import 'test_helpers.dart';

void main() {
  testWidgets('mantiene Enviar por encima de la navegacion del sistema', (
    tester,
  ) async {
    final conversation = Conversation(
      id: 'conversation-1',
      companyCode: 'E00001',
      companyName: 'Empresa de prueba',
      kind: 'general',
      state: 'abierta',
      unreadCount: 0,
      updatedAt: DateTime(2026, 10, 22),
    );
    final content = SharedContent.fromPlatformPayload({
      'files': [
        {'name': 'factura.pdf', 'path': r'C:\cache\factura.pdf', 'size': 100},
      ],
    });

    await tester.pumpWidget(
      ProviderScope(
        overrides: [
          sessionProvider.overrideWith(
            (ref) => FakeSessionController(ref, testSession),
          ),
          conversationsProvider.overrideWith((ref) async => [conversation]),
        ],
        child: MaterialApp(
          builder: (context, child) {
            final mediaQuery = MediaQuery.of(context);
            return MediaQuery(
              data: mediaQuery.copyWith(
                padding: const EdgeInsets.only(bottom: 48),
                viewPadding: const EdgeInsets.only(bottom: 48),
              ),
              child: child!,
            );
          },
          home: Builder(
            builder: (context) => Scaffold(
              body: Center(
                child: FilledButton(
                  onPressed: () =>
                      showShareTargetSheet(context: context, content: content),
                  child: const Text('Compartir'),
                ),
              ),
            ),
          ),
        ),
      ),
    );

    await tester.tap(find.text('Compartir'));
    await tester.pumpAndSettle();

    final sendButton = find.byKey(const Key('send-shared-files'));
    final screenBottom = tester.getBottomRight(find.byType(MaterialApp)).dy;
    expect(sendButton, findsOneWidget);
    expect(
      tester.getBottomRight(sendButton).dy,
      lessThanOrEqualTo(screenBottom - 48),
    );
  });
}
