import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import 'package:gestinemappfull_frontend/app/root_gate.dart';

void main() {
  testWidgets('login page renders by default', (WidgetTester tester) async {
    await tester.pumpWidget(
      const ProviderScope(child: MaterialApp(home: RootGate())),
    );

    expect(find.text('Acceso al despacho'), findsOneWidget);
    expect(find.text('Entrar'), findsOneWidget);
  });
}
