import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:gestinem/features/certificates/domain/certificate_request.dart';
import 'package:gestinem/features/certificates/presentation/certificates_providers.dart';
import 'package:gestinem/features/certificates/presentation/certificates_screen.dart';
import 'package:gestinem/features/platform/features_provider.dart';

void main() {
  testWidgets('permite elegir tramite con certificado central valido', (
    tester,
  ) async {
    await tester.pumpWidget(
      ProviderScope(
        overrides: [
          platformFeaturesProvider.overrideWith(
            (_) async => const PlatformFeatures(certificates: true),
          ),
          certificateStatusProvider.overrideWith(
            (_) async => CertificateStatus(
              configured: true,
              status: 'valid',
              validUntil: DateTime(2027, 9, 10),
            ),
          ),
          certificateTypesProvider.overrideWith(
            (_) async => const [
              CertificateType(
                code: 'AEAT_CORRIENTE',
                organization: 'AEAT',
                name: 'Estar al corriente',
              ),
            ],
          ),
          certificateRequestsProvider.overrideWith((_) async => const []),
        ],
        child: const MaterialApp(home: CertificatesScreen()),
      ),
    );
    await tester.pumpAndSettle();

    expect(
      find.text('Certificado digital preparado hasta 10/9/2027.'),
      findsOneWidget,
    );
    expect(find.byKey(const Key('certificate-type-selector')), findsOneWidget);
    expect(find.byKey(const Key('request-certificate-button')), findsOneWidget);
  });

  testWidgets('bloquea solicitud si el despacho no preparo el certificado', (
    tester,
  ) async {
    await tester.pumpWidget(
      ProviderScope(
        overrides: [
          platformFeaturesProvider.overrideWith(
            (_) async => const PlatformFeatures(certificates: true),
          ),
          certificateStatusProvider.overrideWith(
            (_) async =>
                const CertificateStatus(configured: false, status: 'missing'),
          ),
          certificateTypesProvider.overrideWith((_) async => const []),
          certificateRequestsProvider.overrideWith((_) async => const []),
        ],
        child: const MaterialApp(home: CertificatesScreen()),
      ),
    );
    await tester.pumpAndSettle();

    expect(
      find.text('El despacho todavía no ha preparado tu certificado digital.'),
      findsOneWidget,
    );
    final button = tester.widget<FilledButton>(
      find.byKey(const Key('request-certificate-button')),
    );
    expect(button.onPressed, isNull);
  });

  testWidgets('muestra solicitud completada enlazada a documentos', (
    tester,
  ) async {
    await tester.pumpWidget(
      ProviderScope(
        overrides: [
          platformFeaturesProvider.overrideWith(
            (_) async => const PlatformFeatures(certificates: true),
          ),
          certificateStatusProvider.overrideWith(
            (_) async =>
                const CertificateStatus(configured: true, status: 'valid'),
          ),
          certificateTypesProvider.overrideWith((_) async => const []),
          certificateRequestsProvider.overrideWith(
            (_) async => [
              const CertificateRequest(
                id: 'request-1',
                type: 'AEAT_CORRIENTE',
                name: 'Estar al corriente',
                organization: 'AEAT',
                status: 'completed',
                createdAt: null,
                documentId: 'doc-1',
              ),
            ],
          ),
        ],
        child: const MaterialApp(home: CertificatesScreen()),
      ),
    );
    await tester.pumpAndSettle();

    expect(find.text('Estar al corriente'), findsOneWidget);
    expect(find.text('AEAT · Disponible'), findsOneWidget);
    expect(find.byIcon(Icons.chevron_right), findsOneWidget);
  });
}
