import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:dio/dio.dart';
import 'package:gestinem/core/api/api_client.dart';
import 'package:gestinem/features/auth/presentation/auth_controller.dart';
import 'package:gestinem/features/certificates/domain/certificate_request.dart';
import 'package:gestinem/features/certificates/presentation/certificates_providers.dart';
import 'package:gestinem/features/certificates/presentation/certificates_screen.dart';
import 'package:gestinem/features/platform/features_provider.dart';

import 'test_helpers.dart';

void main() {
  testWidgets('cliente registra solicitud AEAT y refresca el historial', (
    tester,
  ) async {
    final adapter = JsonAdapter({
      'id': 'request-1',
      'certificate_type': 'AEAT_CORRIENTE',
      'certificate_name': 'Estar al corriente',
      'issuing_organization': 'AEAT',
      'status': 'queued',
    }, statusCode: 201);
    var consultas = 0;
    await tester.pumpWidget(
      ProviderScope(
        overrides: [
          apiClientProvider.overrideWithValue(
            ApiClient(
              dio: Dio(BaseOptions(baseUrl: 'https://example.test'))
                ..httpClientAdapter = adapter,
              tokenProvider: () => testSession.token,
            ),
          ),
          platformFeaturesProvider.overrideWith(
            (_) async => const PlatformFeatures(certificates: true),
          ),
          certificateStatusProvider.overrideWith(
            (_) async =>
                const CertificateStatus(configured: true, status: 'valid'),
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
          certificateRequestsProvider.overrideWith((_) async {
            consultas++;
            return const [];
          }),
        ],
        child: const MaterialApp(home: CertificatesScreen()),
      ),
    );
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const Key('certificate-type-selector')));
    await tester.pumpAndSettle();
    await tester.tap(find.text('AEAT · Estar al corriente').last);
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const Key('request-certificate-button')));
    await tester.pumpAndSettle();
    expect(adapter.lastRequest?.method, 'POST');
    expect(adapter.lastRequest?.path, '/client/certificates/requests');
    expect(adapter.lastRequest?.data['certificate_type'], 'AEAT_CORRIENTE');
    expect(adapter.lastRequest?.headers['Authorization'], 'Bearer test-token');
    expect(consultas, 2);
    expect(find.text('Solicitud registrada correctamente.'), findsOneWidget);
  });

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

    expect(find.text('Certificado digital en vigor'), findsOneWidget);
    expect(find.text('Vence: 10/09/2027'), findsOneWidget);
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
      find.text('No consta un certificado digital preparado por el despacho.'),
      findsOneWidget,
    );
    final button = tester.widget<FilledButton>(
      find.byKey(const Key('request-certificate-button')),
    );
    expect(button.onPressed, isNull);
  });

  testWidgets('solicita los datos obligatorios del certificado contratista', (
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
          certificateTypesProvider.overrideWith(
            (_) async => const [
              CertificateType(
                code: 'AEAT_CONTRATISTAS',
                organization: 'AEAT',
                name: 'Contratistas y subcontratistas',
                parameters: [
                  CertificateParameter(
                    key: 'contracting_party_tax_id',
                    label: 'CIF/NIF de la empresa con la que contrata',
                    type: 'tax_id',
                    required: true,
                  ),
                  CertificateParameter(
                    key: 'contracting_party_name',
                    label: 'Nombre o razon social de la empresa',
                    type: 'text',
                    required: true,
                  ),
                ],
              ),
            ],
          ),
          certificateRequestsProvider.overrideWith((_) async => const []),
        ],
        child: const MaterialApp(home: CertificatesScreen()),
      ),
    );
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const Key('certificate-type-selector')));
    await tester.pumpAndSettle();
    await tester.tap(find.text('AEAT · Contratistas y subcontratistas').last);
    await tester.pumpAndSettle();

    final field = find.byKey(
      const Key('certificate-parameter-contracting_party_tax_id'),
    );
    expect(field, findsOneWidget);
    expect(
      find.byKey(const Key('certificate-parameter-contracting_party_name')),
      findsOneWidget,
    );
    var button = tester.widget<FilledButton>(
      find.byKey(const Key('request-certificate-button')),
    );
    expect(button.onPressed, isNull);
    await tester.enterText(field, 'B12345678');
    await tester.pump();
    button = tester.widget<FilledButton>(
      find.byKey(const Key('request-certificate-button')),
    );
    expect(button.onPressed, isNull);
    await tester.enterText(
      find.byKey(const Key('certificate-parameter-contracting_party_name')),
      'Empresa contratante SL',
    );
    await tester.pump();
    button = tester.widget<FilledButton>(
      find.byKey(const Key('request-certificate-button')),
    );
    expect(button.onPressed, isNotNull);
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
    expect(
      find.byKey(const Key('certificate-request-actions-request-1')),
      findsOneWidget,
    );
  });

  testWidgets('eliminar solicitud completada pide confirmacion y refresca', (
    tester,
  ) async {
    final adapter = JsonAdapter({'deleted': true, 'id': 'request-1'});
    var consultas = 0;
    await _pumpRequestActions(
      tester,
      adapter,
      'completed',
      onList: () => consultas++,
    );
    await tester.ensureVisible(
      find.byKey(const Key('certificate-request-actions-request-1')),
    );
    await tester.tap(
      find.byKey(const Key('certificate-request-actions-request-1')),
    );
    await tester.pumpAndSettle();
    await tester.tap(find.text('Eliminar solicitud'));
    await tester.pumpAndSettle();
    expect(adapter.lastRequest, isNull);
    expect(
      find.textContaining('El despacho conservará el historial'),
      findsOneWidget,
    );
    await tester.tap(
      find.byKey(const Key('confirm-remove-certificate-request')),
    );
    await tester.pumpAndSettle();
    expect(adapter.lastRequest?.method, 'DELETE');
    expect(
      adapter.lastRequest?.path,
      '/client/certificates/requests/request-1',
    );
    expect(adapter.lastRequest?.headers['Authorization'], 'Bearer test-token');
    expect(consultas, 2);
    expect(
      find.text('Solicitud eliminada. Ya puedes pedir otra.'),
      findsOneWidget,
    );
  });

  testWidgets('volver de la confirmacion no elimina nada', (tester) async {
    final adapter = JsonAdapter({'deleted': true});
    await _pumpRequestActions(tester, adapter, 'needs_action');
    await tester.ensureVisible(
      find.byKey(const Key('certificate-request-actions-request-1')),
    );
    await tester.tap(
      find.byKey(const Key('certificate-request-actions-request-1')),
    );
    await tester.pumpAndSettle();
    await tester.tap(find.text('Eliminar solicitud'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Volver'));
    await tester.pumpAndSettle();
    expect(adapter.lastRequest, isNull);
  });

  testWidgets('reintenta la solicitud con intervencion sin crear otra', (
    tester,
  ) async {
    final adapter = JsonAdapter({'id': 'request-1', 'status': 'queued'});
    await _pumpRequestActions(tester, adapter, 'needs_action');
    await tester.ensureVisible(
      find.byKey(const Key('certificate-request-actions-request-1')),
    );
    await tester.tap(
      find.byKey(const Key('certificate-request-actions-request-1')),
    );
    await tester.pumpAndSettle();
    await tester.tap(find.text('Reintentar solicitud'));
    await tester.pumpAndSettle();
    expect(adapter.lastRequest?.method, 'POST');
    expect(
      adapter.lastRequest?.path,
      '/client/certificates/requests/request-1/retry',
    );
    expect(find.text('Solicitud preparada para reintentar.'), findsOneWidget);
  });

  testWidgets('en tramitacion no ofrece eliminar ni reintentar', (
    tester,
  ) async {
    await _pumpRequestActions(tester, JsonAdapter({}), 'processing');
    expect(
      find.byKey(const Key('certificate-request-actions-request-1')),
      findsNothing,
    );
  });

  testWidgets('error al eliminar conserva solicitud y muestra motivo', (
    tester,
  ) async {
    final adapter = JsonAdapter({
      'detail': 'La solicitud sigue en tramitación.',
    }, statusCode: 409);
    await _pumpRequestActions(tester, adapter, 'failed');
    await tester.ensureVisible(
      find.byKey(const Key('certificate-request-actions-request-1')),
    );
    await tester.tap(
      find.byKey(const Key('certificate-request-actions-request-1')),
    );
    await tester.pumpAndSettle();
    await tester.tap(find.text('Eliminar solicitud'));
    await tester.pumpAndSettle();
    await tester.tap(
      find.byKey(const Key('confirm-remove-certificate-request')),
    );
    await tester.pumpAndSettle();
    expect(find.text('La solicitud sigue en tramitación.'), findsOneWidget);
    expect(find.text('Estar al corriente'), findsOneWidget);
  });

  testWidgets('resguardo pendiente permite comprobar pero no eliminar', (
    tester,
  ) async {
    final adapter = JsonAdapter({});
    await _pumpRequestActions(
      tester,
      adapter,
      'awaiting_issuance',
      submittedAt: DateTime.utc(2026, 9, 18),
      receiptDocumentId: 'resguardo-1',
    );
    expect(
      find.textContaining('Pendiente de emisión en Hacienda'),
      findsOneWidget,
    );
    expect(find.textContaining('Resguardo recibido'), findsOneWidget);
    expect(find.textContaining('Disponible'), findsNothing);
    await tester.ensureVisible(
      find.byKey(const Key('certificate-request-actions-request-1')),
    );
    await tester.tap(
      find.byKey(const Key('certificate-request-actions-request-1')),
    );
    await tester.pumpAndSettle();
    expect(find.text('Comprobar emisión'), findsOneWidget);
    expect(find.text('Eliminar solicitud'), findsNothing);
    expect(find.text('Cancelar solicitud'), findsNothing);
    await tester.tap(find.text('Comprobar emisión'));
    await tester.pumpAndSettle();
    expect(
      adapter.lastRequest?.path,
      '/client/certificates/requests/request-1/retry',
    );
    expect(
      find.textContaining('No se presentará otra solicitud'),
      findsOneWidget,
    );
  });

  testWidgets('certificado definitivo muestra resultado negativo', (
    tester,
  ) async {
    await _pumpRequestActions(
      tester,
      JsonAdapter({}),
      'completed',
      certificateResult: 'NEGATIVO',
    );
    expect(find.textContaining('Disponible · Negativo'), findsOneWidget);
    expect(find.textContaining('Positivo'), findsNothing);
  });
}

Future<void> _pumpRequestActions(
  WidgetTester tester,
  JsonAdapter adapter,
  String status, {
  VoidCallback? onList,
  DateTime? submittedAt,
  String? receiptDocumentId,
  String? certificateResult,
}) async {
  await tester.pumpWidget(
    ProviderScope(
      overrides: [
        apiClientProvider.overrideWithValue(
          ApiClient(
            dio: Dio(BaseOptions(baseUrl: 'https://example.test'))
              ..httpClientAdapter = adapter,
            tokenProvider: () => testSession.token,
          ),
        ),
        platformFeaturesProvider.overrideWith(
          (_) async => const PlatformFeatures(certificates: true),
        ),
        certificateStatusProvider.overrideWith(
          (_) async =>
              const CertificateStatus(configured: true, status: 'valid'),
        ),
        certificateTypesProvider.overrideWith((_) async => const []),
        certificateRequestsProvider.overrideWith((_) async {
          onList?.call();
          return [
            CertificateRequest(
              id: 'request-1',
              type: 'AEAT_CORRIENTE',
              name: 'Estar al corriente',
              organization: 'AEAT',
              status: status,
              createdAt: null,
              documentId: 'doc-1',
              submittedAt: submittedAt,
              receiptDocumentId: receiptDocumentId,
              certificateResult: certificateResult,
            ),
          ];
        }),
      ],
      child: const MaterialApp(home: CertificatesScreen()),
    ),
  );
  await tester.pumpAndSettle();
}
