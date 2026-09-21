import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:gestinem/features/certificates/domain/certificate_request.dart';
import 'package:gestinem/features/certificates/presentation/digital_certificate_card.dart';
import 'package:gestinem/features/messaging/domain/conversation.dart';
import 'package:gestinem/features/messaging/presentation/messaging_providers.dart';
import 'package:go_router/go_router.dart';

void main() {
  testWidgets('muestra vencimiento y datos sin acceso al archivo', (
    tester,
  ) async {
    await tester.pumpWidget(
      const ProviderScope(
        child: MaterialApp(
          home: Scaffold(
            body: DigitalCertificateCard(
              status: AsyncData(
                CertificateStatus(
                  configured: true,
                  status: 'valid',
                  commonName: 'Empresa Uno',
                  issuer: 'FNMT',
                  validUntil: null,
                ),
              ),
            ),
          ),
        ),
      ),
    );

    expect(find.text('Certificado digital en vigor'), findsOneWidget);
    expect(find.text('Titular: Empresa Uno'), findsOneWidget);
    expect(find.text('Emisor: FNMT'), findsOneWidget);
    expect(find.textContaining('custodiado por el despacho'), findsOneWidget);
    expect(find.byIcon(Icons.download), findsNothing);
  });

  testWidgets('avisa cuando el certificado vence pronto', (tester) async {
    await tester.pumpWidget(
      ProviderScope(
        child: MaterialApp(
          home: Scaffold(
            body: DigitalCertificateCard(
              status: AsyncData(
                CertificateStatus(
                  configured: true,
                  status: 'valid',
                  validUntil: DateTime.now().add(const Duration(days: 10)),
                ),
              ),
            ),
          ),
        ),
      ),
    );

    expect(find.text('Certificado digital próximo a vencer'), findsOneWidget);
    expect(
      find.byKey(const Key('digital-certificate-contact-office')),
      findsOneWidget,
    );
  });

  testWidgets('sin certificado abre borrador para el despacho', (tester) async {
    final router = GoRouter(
      initialLocation: '/documentation',
      routes: [
        GoRoute(
          path: '/documentation',
          builder: (_, _) => const Scaffold(
            body: DigitalCertificateCard(
              status: AsyncData(
                CertificateStatus(configured: false, status: 'missing'),
              ),
            ),
          ),
        ),
        GoRoute(
          path: '/conversation/:id',
          builder: (_, state) => Scaffold(
            body: Text('${state.pathParameters['id']}: ${state.extra}'),
          ),
        ),
      ],
    );
    addTearDown(router.dispose);
    await tester.pumpWidget(
      ProviderScope(
        overrides: [
          conversationsProvider.overrideWith(
            (_) async => [
              Conversation(
                id: 'fiscal-1',
                companyCode: 'E00001',
                companyName: 'Empresa Uno',
                kind: 'fiscal',
                state: 'abierta',
                unreadCount: 0,
                updatedAt: DateTime(2026),
              ),
            ],
          ),
        ],
        child: MaterialApp.router(routerConfig: router),
      ),
    );
    await tester.pumpAndSettle();

    expect(
      find.text('No consta un certificado digital preparado por el despacho.'),
      findsOneWidget,
    );
    await tester.tap(
      find.byKey(const Key('digital-certificate-contact-office')),
    );
    await tester.pumpAndSettle();

    expect(find.textContaining('fiscal-1: Hola,'), findsOneWidget);
    expect(find.textContaining('cómo incorporarlo'), findsOneWidget);
  });
}
