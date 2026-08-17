import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:gestinem/features/auth/presentation/auth_controller.dart';
import 'package:gestinem/features/auth/presentation/login_screen.dart';

import 'test_helpers.dart';

void main() {
  testWidgets('login muestra acceso cliente y personal', (tester) async {
    await tester.pumpWidget(ProviderScope(
      overrides: [sessionProvider.overrideWith((ref) => FakeSessionController(ref, null))],
      child: const MaterialApp(home: LoginScreen()),
    ));

    expect(find.text('Gestinem'), findsOneWidget);
    expect(find.byKey(const Key('login-email')), findsOneWidget);
    expect(find.byKey(const Key('login-password')), findsOneWidget);
    expect(find.byKey(const Key('client-login-button')), findsOneWidget);
    expect(find.byKey(const Key('staff-login-button')), findsOneWidget);
  });
}
