import 'package:dio/dio.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:gestinem/core/api/api_client.dart';
import 'package:gestinem/features/auth/presentation/auth_controller.dart';
import 'package:gestinem/features/invoicing/domain/client_invoice.dart';
import 'package:gestinem/features/invoicing/domain/invoice_status.dart';
import 'package:gestinem/features/invoicing/presentation/invoicing_providers.dart';
import 'package:gestinem/features/invoicing/presentation/invoicing_screen.dart';
import 'package:gestinem/features/invoicing/presentation/customer_list_screen.dart';
import 'package:gestinem/features/invoicing/presentation/invoice_detail_screen.dart';

import 'test_helpers.dart';

void main() {
  // -- Modelo InvoiceStatus --
  group('InvoiceStatus', () {
    test('fromString parsea todos los estados', () {
      expect(InvoiceStatus.fromString('draft'), InvoiceStatus.draft);
      expect(
        InvoiceStatus.fromString('issued_pending_processing'),
        InvoiceStatus.issuedPendingProcessing,
      );
      expect(InvoiceStatus.fromString('claimed'), InvoiceStatus.claimed);
      expect(InvoiceStatus.fromString('imported'), InvoiceStatus.imported);
      expect(InvoiceStatus.fromString('rendered'), InvoiceStatus.rendered);
      expect(InvoiceStatus.fromString('emailed'), InvoiceStatus.emailed);
      expect(
        InvoiceStatus.fromString('processing_error'),
        InvoiceStatus.processingError,
      );
      expect(InvoiceStatus.fromString('cancelled'), InvoiceStatus.cancelled);
      expect(InvoiceStatus.fromString('replaced'), InvoiceStatus.replaced);
    });

    test('estado desconocido devuelve draft', () {
      expect(InvoiceStatus.fromString('unknown'), InvoiceStatus.draft);
    });

    test('isDraft, isProcessing, isComplete, isError', () {
      expect(InvoiceStatus.draft.isDraft, true);
      expect(InvoiceStatus.draft.isProcessing, false);
      expect(InvoiceStatus.issuedPendingProcessing.isProcessing, true);
      expect(InvoiceStatus.claimed.isProcessing, true);
      expect(InvoiceStatus.imported.isProcessing, true);
      expect(InvoiceStatus.rendered.isComplete, true);
      expect(InvoiceStatus.emailed.isComplete, true);
      expect(InvoiceStatus.processingError.isError, true);
      expect(InvoiceStatus.cancelled.isError, false);
    });

    test('labels', () {
      expect(InvoiceStatus.draft.label, 'Borrador');
      expect(InvoiceStatus.processingError.label, 'Error');
      expect(InvoiceStatus.emailed.label, 'Email enviado');
    });
  });

  // -- Modelo ClientInvoice --
  group('ClientInvoice', () {
    test('fromJson parsea correctamente', () {
      final inv = ClientInvoice.fromJson({
        'id': 'inv-1',
        'fiscal_year': 2026,
        'series_code': 'WEB',
        'invoice_number': 42,
        'invoice_date': '2026-03-15',
        'status': 'emailed',
        'customer_id': 'cust-1',
        'subtotal': '1000.00',
        'total_vat': '210.00',
        'withholding_rate': '15',
        'withholding_amount': '150.00',
        'total': '1060.00',
        'currency': 'EUR',
        'lines': [
          {
            'description': 'Servicio A',
            'quantity': '2',
            'unit_price': '500.00',
            'vat_rate': '21.00',
            'line_total': '1000.00',
            'vat_amount': '210.00',
          },
        ],
      });

      expect(inv.id, 'inv-1');
      expect(inv.displayNumber, 'WEB-000042');
      expect(inv.status, InvoiceStatus.emailed);
      expect(inv.lines.length, 1);
      expect(inv.lines.first.description, 'Servicio A');
      expect(inv.total, '1060.00');
      expect(inv.withholdingRate, '15');
    });

    test('displayNumber borrador', () {
      const draft = ClientInvoice(
        id: 'd-1',
        fiscalYear: 2026,
        status: InvoiceStatus.draft,
        customerId: 'c-1',
      );
      expect(draft.displayNumber, 'Borrador');
    });

    test('fromJson con campos minimos', () {
      final inv = ClientInvoice.fromJson({'id': 'min-1'});
      expect(inv.id, 'min-1');
      expect(inv.seriesCode, 'WEB');
      expect(inv.status, InvoiceStatus.draft);
      expect(inv.lines, isEmpty);
    });
  });

  // -- Modelo InvoiceCustomer --
  group('InvoiceCustomer', () {
    test('fromJson parsea campos', () {
      final customer = InvoiceCustomer.fromJson({
        'id': 'cust-1',
        'tax_id': 'B12345678',
        'legal_name': 'Empresa Test SL',
        'address': 'Calle Falsa 123',
        'postal_code': '28001',
        'city': 'Madrid',
        'province': 'Madrid',
        'country': 'ES',
        'email': 'test@example.com',
        'phone': '600000000',
        'default_vat_rate': '21.00',
        'active': true,
      });

      expect(customer.taxId, 'B12345678');
      expect(customer.legalName, 'Empresa Test SL');
      expect(customer.city, 'Madrid');
      expect(customer.active, true);
    });

    test('fromJson con campos minimos', () {
      final customer = InvoiceCustomer.fromJson({'id': 'c-min'});
      expect(customer.id, 'c-min');
      expect(customer.taxId, '');
      expect(customer.country, 'ES');
      expect(customer.active, true);
    });
  });

  // -- InvoiceLine --
  group('InvoiceLine', () {
    test('toJson serializa solo campos editables', () {
      const line = InvoiceLine(
        description: 'Servicio',
        quantity: '3',
        unitPrice: '100.00',
        discountPercent: '10',
        vatRate: '21.00',
        lineTotal: '270.00',
        vatAmount: '56.70',
      );
      final json = line.toJson();
      expect(json['description'], 'Servicio');
      expect(json['quantity'], '3');
      expect(json['unit_price'], '100.00');
      expect(json.containsKey('line_total'), false);
      expect(json.containsKey('vat_amount'), false);
    });
  });

  // -- InvoicingScreen - feature gate --
  group('InvoicingScreen - feature gate', () {
    testWidgets('muestra mensaje cuando facturacion esta desactivada', (
      tester,
    ) async {
      await tester.pumpWidget(
        ProviderScope(
          overrides: [
            sessionProvider.overrideWith((ref) => FakeSessionController(ref)),
            apiClientProvider.overrideWithValue(
              ApiClient(
                dio: Dio(BaseOptions(baseUrl: 'https://example.test'))
                  ..httpClientAdapter = JsonAdapter({'enabled': false}),
                tokenProvider: () => testSession.token,
              ),
            ),
            invoicingConfigProvider.overrideWith(
              (ref) async => {'enabled': false},
            ),
          ],
          child: const MaterialApp(home: InvoicingScreen()),
        ),
      );
      await tester.pumpAndSettle();

      expect(
        find.text('La facturacion online no esta habilitada.'),
        findsOneWidget,
      );
    });

    testWidgets('muestra pestanas cuando facturacion esta activada', (
      tester,
    ) async {
      await tester.pumpWidget(
        ProviderScope(
          overrides: [
            sessionProvider.overrideWith((ref) => FakeSessionController(ref)),
            apiClientProvider.overrideWithValue(
              ApiClient(
                dio: Dio(BaseOptions(baseUrl: 'https://example.test'))
                  ..httpClientAdapter = JsonAdapter([]),
                tokenProvider: () => testSession.token,
              ),
            ),
            invoicingConfigProvider.overrideWith(
              (ref) async => {'enabled': true},
            ),
            invoiceDraftsProvider.overrideWith(
              (ref) async => <ClientInvoice>[],
            ),
          ],
          child: const MaterialApp(home: InvoicingScreen()),
        ),
      );
      await tester.pumpAndSettle();

      expect(find.text('Borradores'), findsOneWidget);
      expect(find.text('Emitidas'), findsOneWidget);
      expect(find.byType(FloatingActionButton), findsOneWidget);
    });
  });

  // -- Borradores --
  group('InvoicingScreen - borradores', () {
    testWidgets('muestra mensaje vacio si no hay borradores', (tester) async {
      await tester.pumpWidget(
        ProviderScope(
          overrides: [
            sessionProvider.overrideWith((ref) => FakeSessionController(ref)),
            apiClientProvider.overrideWithValue(
              ApiClient(
                dio: Dio(BaseOptions(baseUrl: 'https://example.test'))
                  ..httpClientAdapter = JsonAdapter([]),
                tokenProvider: () => testSession.token,
              ),
            ),
            invoicingConfigProvider.overrideWith(
              (ref) async => {'enabled': true},
            ),
            invoiceDraftsProvider.overrideWith(
              (ref) async => <ClientInvoice>[],
            ),
          ],
          child: const MaterialApp(home: InvoicingScreen()),
        ),
      );
      await tester.pumpAndSettle();

      expect(find.text('No hay borradores.'), findsOneWidget);
    });

    testWidgets('muestra borrador con icono de edicion', (tester) async {
      final drafts = [
        ClientInvoice.fromJson({
          'id': 'draft-1',
          'status': 'draft',
          'customer_id': 'c-1',
          'total': '500.00',
          'invoice_date': '2026-08-20',
        }),
      ];

      await tester.pumpWidget(
        ProviderScope(
          overrides: [
            sessionProvider.overrideWith((ref) => FakeSessionController(ref)),
            apiClientProvider.overrideWithValue(
              ApiClient(
                dio: Dio(BaseOptions(baseUrl: 'https://example.test'))
                  ..httpClientAdapter = JsonAdapter([]),
                tokenProvider: () => testSession.token,
              ),
            ),
            invoicingConfigProvider.overrideWith(
              (ref) async => {'enabled': true},
            ),
            invoiceDraftsProvider.overrideWith((ref) async => drafts),
          ],
          child: const MaterialApp(home: InvoicingScreen()),
        ),
      );
      await tester.pumpAndSettle();

      expect(find.text('Borrador'), findsOneWidget);
      expect(find.byIcon(Icons.edit_note), findsOneWidget);
      expect(find.textContaining('500.00'), findsOneWidget);
    });
  });

  // -- Clientes --
  group('CustomerListScreen', () {
    testWidgets('muestra lista de clientes', (tester) async {
      final customers = [
        InvoiceCustomer.fromJson({
          'id': 'c-1',
          'tax_id': 'B12345678',
          'legal_name': 'Empresa Alfa SL',
          'active': true,
        }),
        InvoiceCustomer.fromJson({
          'id': 'c-2',
          'tax_id': 'A87654321',
          'legal_name': 'Corp Beta SA',
          'active': false,
        }),
      ];

      await tester.pumpWidget(
        ProviderScope(
          overrides: [
            sessionProvider.overrideWith((ref) => FakeSessionController(ref)),
            apiClientProvider.overrideWithValue(
              ApiClient(
                dio: Dio(BaseOptions(baseUrl: 'https://example.test'))
                  ..httpClientAdapter = JsonAdapter({}),
                tokenProvider: () => testSession.token,
              ),
            ),
            invoiceCustomersProvider.overrideWith((ref) async => customers),
          ],
          child: const MaterialApp(home: CustomerListScreen()),
        ),
      );
      await tester.pumpAndSettle();

      expect(find.text('Empresa Alfa SL'), findsOneWidget);
      expect(find.text('B12345678'), findsOneWidget);
      expect(find.text('Corp Beta SA'), findsOneWidget);
      expect(find.text('Inactivo'), findsOneWidget);
    });

    testWidgets('muestra mensaje vacio sin clientes', (tester) async {
      await tester.pumpWidget(
        ProviderScope(
          overrides: [
            sessionProvider.overrideWith((ref) => FakeSessionController(ref)),
            apiClientProvider.overrideWithValue(
              ApiClient(
                dio: Dio(BaseOptions(baseUrl: 'https://example.test'))
                  ..httpClientAdapter = JsonAdapter({}),
                tokenProvider: () => testSession.token,
              ),
            ),
            invoiceCustomersProvider.overrideWith(
              (ref) async => <InvoiceCustomer>[],
            ),
          ],
          child: const MaterialApp(home: CustomerListScreen()),
        ),
      );
      await tester.pumpAndSettle();

      expect(find.text('No hay clientes registrados.'), findsOneWidget);
    });
  });

  // -- Detalle factura --
  group('InvoiceDetailScreen', () {
    testWidgets('muestra detalle con estado y totales', (tester) async {
      final invoice = ClientInvoice.fromJson({
        'id': 'inv-100',
        'fiscal_year': 2026,
        'series_code': 'WEB',
        'invoice_number': 7,
        'invoice_date': '2026-08-01',
        'status': 'emailed',
        'customer_id': 'c-1',
        'subtotal': '1000.00',
        'total_vat': '210.00',
        'withholding_rate': '15',
        'withholding_amount': '150.00',
        'total': '1060.00',
        'currency': 'EUR',
        'payment_method': 'Transferencia',
        'notes': 'Servicio mensual',
        'lines': [
          {
            'description': 'Consultoria',
            'quantity': '10',
            'unit_price': '100.00',
            'vat_rate': '21.00',
            'line_total': '1000.00',
          },
        ],
      });

      await tester.pumpWidget(
        ProviderScope(
          overrides: [
            sessionProvider.overrideWith((ref) => FakeSessionController(ref)),
            invoiceDetailProvider(
              'inv-100',
            ).overrideWith((ref) async => invoice),
          ],
          child: const MaterialApp(
            home: InvoiceDetailScreen(invoiceId: 'inv-100'),
          ),
        ),
      );
      await tester.pumpAndSettle();

      expect(find.text('WEB-000007'), findsOneWidget);
      expect(find.text('Email enviado'), findsOneWidget);
      expect(find.text('2026-08-01'), findsOneWidget);
      expect(find.text('Transferencia'), findsOneWidget);
      expect(find.text('Servicio mensual'), findsOneWidget);
      expect(find.text('Consultoria'), findsOneWidget);
      expect(find.textContaining('1000.00'), findsWidgets);
      expect(find.textContaining('210.00'), findsWidgets);
      expect(find.textContaining('1060.00'), findsWidgets);
    });

    testWidgets('factura con error muestra banner rojo', (tester) async {
      final invoice = ClientInvoice.fromJson({
        'id': 'inv-err',
        'status': 'processing_error',
        'customer_id': 'c-1',
      });

      await tester.pumpWidget(
        ProviderScope(
          overrides: [
            sessionProvider.overrideWith((ref) => FakeSessionController(ref)),
            invoiceDetailProvider(
              'inv-err',
            ).overrideWith((ref) async => invoice),
          ],
          child: const MaterialApp(
            home: InvoiceDetailScreen(invoiceId: 'inv-err'),
          ),
        ),
      );
      await tester.pumpAndSettle();

      expect(find.text('Error'), findsOneWidget);
      expect(find.byIcon(Icons.error_outline), findsOneWidget);
    });

    testWidgets('factura en proceso muestra banner naranja', (tester) async {
      final invoice = ClientInvoice.fromJson({
        'id': 'inv-proc',
        'status': 'claimed',
        'customer_id': 'c-1',
      });

      await tester.pumpWidget(
        ProviderScope(
          overrides: [
            sessionProvider.overrideWith((ref) => FakeSessionController(ref)),
            invoiceDetailProvider(
              'inv-proc',
            ).overrideWith((ref) async => invoice),
          ],
          child: const MaterialApp(
            home: InvoiceDetailScreen(invoiceId: 'inv-proc'),
          ),
        ),
      );
      await tester.pumpAndSettle();

      expect(find.text('En proceso'), findsOneWidget);
      expect(find.byIcon(Icons.hourglass_empty), findsOneWidget);
    });
  });

  // -- Idempotencia de emision --
  group('InvoicingRepository.issueDraft', () {
    test('envia Idempotency-Key en cabecera', () async {
      final adapter = JsonAdapter({
        'id': 'inv-new',
        'status': 'issued_pending_processing',
        'customer_id': 'c-1',
        'invoice_number': 1,
        'series_code': 'WEB',
      });
      final api = ApiClient(
        dio: Dio(BaseOptions(baseUrl: 'https://example.test'))
          ..httpClientAdapter = adapter,
        tokenProvider: () => testSession.token,
      );
      final container = ProviderContainer(
        overrides: [
          sessionProvider.overrideWith((ref) => FakeSessionController(ref)),
          apiClientProvider.overrideWithValue(api),
        ],
      );
      addTearDown(container.dispose);

      final repo = container.read(invoicingRepositoryProvider);
      final result = await repo.issueDraft('draft-1');

      expect(result.status, InvoiceStatus.issuedPendingProcessing);
      expect(
        adapter.lastRequest!.path,
        '/client/invoicing/drafts/draft-1/issue',
      );
      expect(adapter.lastRequest!.headers.containsKey('Idempotency-Key'), true);
      expect(
        (adapter.lastRequest!.headers['Idempotency-Key'] as String).isNotEmpty,
        true,
      );
    });
  });
}
