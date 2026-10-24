import 'dart:typed_data';

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
    testWidgets('muestra detalle con estados separados y totales', (
      tester,
    ) async {
      final invoice = ClientInvoice.fromJson({
        'id': 'inv-100',
        'fiscal_year': 2026,
        'series_code': 'WEB',
        'invoice_number': 7,
        'invoice_date': '2026-08-01',
        'status': 'emailed',
        'invoice_status': 'issued',
        'fiscal_status': 'pending',
        'pdf_status': 'generated',
        'delivery_status': 'sent',
        'accounting_sync_status': 'pending',
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
      // Estados separados: emision, PDF y entrega visibles por separado.
      expect(find.text('Emitida'), findsOneWidget);
      expect(find.text('Generado'), findsOneWidget);
      expect(find.text('Enviado'), findsOneWidget);
      expect(find.text('2026-08-01'), findsOneWidget);
      expect(find.text('Transferencia'), findsOneWidget);
      expect(find.text('Servicio mensual'), findsOneWidget);
      expect(find.text('Consultoria'), findsOneWidget);
      expect(find.textContaining('1000.00'), findsWidgets);
      expect(find.textContaining('210.00'), findsWidgets);
      expect(find.textContaining('1060.00'), findsWidgets);
    });

    testWidgets(
      'incidencia fiscal se muestra sin confundirse con un problema contable',
      (tester) async {
        final invoice = ClientInvoice.fromJson({
          'id': 'inv-err',
          'status': 'processing_error',
          'invoice_status': 'issued',
          'fiscal_status': 'incident',
          'accounting_sync_status': 'pending',
          'customer_id': 'c-1',
        });

        await tester.pumpWidget(
          ProviderScope(
            overrides: [
              sessionProvider.overrideWith(
                (ref) => FakeSessionController(ref),
              ),
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

        // Aparece tanto en el chip de estado fiscal como en el aviso.
        expect(find.text('Incidencia fiscal'), findsWidgets);
        expect(find.byIcon(Icons.warning_amber_rounded), findsOneWidget);
        // El aviso contable (distinto) no aparece: accounting_sync_status=pending.
        expect(find.text('Pendiente de revision contable'), findsNothing);
      },
    );

    testWidgets(
      'problema contable se muestra sin afectar al estado fiscal',
      (tester) async {
        final invoice = ClientInvoice.fromJson({
          'id': 'inv-acc',
          'status': 'imported',
          'invoice_status': 'issued',
          'fiscal_status': 'accepted',
          'accounting_sync_status': 'review_required',
          'customer_id': 'c-1',
        });

        await tester.pumpWidget(
          ProviderScope(
            overrides: [
              sessionProvider.overrideWith(
                (ref) => FakeSessionController(ref),
              ),
              invoiceDetailProvider(
                'inv-acc',
              ).overrideWith((ref) async => invoice),
            ],
            child: const MaterialApp(
              home: InvoiceDetailScreen(invoiceId: 'inv-acc'),
            ),
          ),
        );
        await tester.pumpAndSettle();

        expect(find.text('Pendiente de revision contable'), findsOneWidget);
        // El estado fiscal sigue siendo "Aceptado por la AEAT": ningun
        // aviso fiscal se muestra.
        expect(find.text('Incidencia fiscal'), findsNothing);
      },
    );
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

  // -- Rectificativas y anulaciones (Etapa 7/9) --
  group('InvoicingRepository rectify/cancel', () {
    test('rectifyInvoice envia motivo, lineas e Idempotency-Key', () async {
      final adapter = JsonAdapter({
        'id': 'inv-rect',
        'status': 'issued_pending_processing',
        'invoice_status': 'issued',
        'customer_id': 'c-1',
        'rectifies_invoice_id': 'inv-orig',
        'invoice_number': 2,
        'series_code': 'APP',
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
      final result = await repo.rectifyInvoice(
        'inv-orig',
        reason: 'Precio incorrecto',
        lines: [
          {'description': 'Servicio corregido', 'quantity': '1', 'unit_price': '90'},
        ],
      );

      expect(result.rectifiesInvoiceId, 'inv-orig');
      expect(adapter.lastRequest!.path, '/client/invoicing/invoices/inv-orig/rectify');
      expect(adapter.lastRequest!.headers.containsKey('Idempotency-Key'), true);
      final body = adapter.lastRequest!.data as Map<String, dynamic>;
      expect(body['reason'], 'Precio incorrecto');
      expect((body['lines'] as List).single['description'], 'Servicio corregido');
    });

    test('cancelInvoice envia el motivo', () async {
      final adapter = JsonAdapter({
        'id': 'inv-1',
        'status': 'cancelled',
        'invoice_status': 'cancelled',
        'cancellation_reason': 'Duplicada',
        'customer_id': 'c-1',
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
      final result = await repo.cancelInvoice('inv-1', reason: 'Duplicada');

      expect(result.invoiceStatus, InvoiceLifecycleStatus.cancelled);
      expect(adapter.lastRequest!.path, '/client/invoicing/invoices/inv-1/cancel');
      final body = adapter.lastRequest!.data as Map<String, dynamic>;
      expect(body['reason'], 'Duplicada');
    });
  });

  // -- Descarga de PDF --
  group('InvoicingRepository.downloadInvoicePdf', () {
    test('descarga los bytes del PDF desde la ruta esperada', () async {
      final adapter = _BytesAdapter(Uint8List.fromList([0x25, 0x50, 0x44, 0x46]));
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
      final bytes = await repo.downloadInvoicePdf('inv-1');

      expect(bytes, [0x25, 0x50, 0x44, 0x46]);
      expect(adapter.lastPath, '/client/invoicing/invoices/inv-1/pdf');
    });
  });

  // -- Catalogo de productos y servicios --
  group('InvoicingRepository catalogo', () {
    test('listCatalogItems envia busqueda y filtro de activos', () async {
      final adapter = JsonAdapter({
        'items': [
          {'id': 'cat-1', 'item_type': 'service', 'description': 'Hora de consultoria'},
        ],
        'total': 1,
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
      final result = await repo.listCatalogItems(q: 'consultoria', active: true);

      expect((result['items'] as List).length, 1);
      expect(adapter.lastRequest!.queryParameters['q'], 'consultoria');
      expect(adapter.lastRequest!.queryParameters['active'], true);
    });

    test('createCatalogItem envia item_type, descripcion y precio', () async {
      final adapter = JsonAdapter({
        'id': 'cat-new',
        'item_type': 'product',
        'description': 'Licencia anual',
        'unit_price': '199.00',
        'vat_rate': '21.00',
        'withholding_rate': '0',
        'active': true,
        'revision': 1,
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
      final item = await repo.createCatalogItem({
        'item_type': 'product',
        'description': 'Licencia anual',
        'unit_price': '199.00',
      });

      expect(item.id, 'cat-new');
      expect(item.isProduct, true);
      expect(adapter.lastRequest!.path, '/client/invoicing/catalog/items');
    });
  });

  // -- Facturas desktop: solo lectura --
  group('ClientInvoice origen desktop', () {
    test('una factura de origen desktop no se puede rectificar ni anular', () {
      final invoice = ClientInvoice.fromJson({
        'id': 'inv-desktop-1',
        'status': 'emailed',
        'invoice_status': 'issued',
        'source_system': 'desktop',
        'customer_id': 'c-1',
      });

      expect(invoice.isReadOnlyFromDesktop, true);
      expect(invoice.canRectify, false);
      expect(invoice.canCancel, false);
    });

    test('una factura client_app emitida si se puede rectificar y anular', () {
      final invoice = ClientInvoice.fromJson({
        'id': 'inv-app-1',
        'status': 'emailed',
        'invoice_status': 'issued',
        'source_system': 'client_app',
        'customer_id': 'c-1',
      });

      expect(invoice.isReadOnlyFromDesktop, false);
      expect(invoice.canRectify, true);
      expect(invoice.canCancel, true);
    });
  });

  // -- Diseno responsive (seccion 19: web/movil) --
  group('InvoicingScreen responsive', () {
    testWidgets('no desborda en ancho movil estrecho', (tester) async {
      tester.view.physicalSize = const Size(360, 800);
      tester.view.devicePixelRatio = 1.0;
      addTearDown(tester.view.resetPhysicalSize);
      addTearDown(tester.view.resetDevicePixelRatio);

      final adapter = JsonAdapter({'enabled': true, 'fiscal_year': 2026, 'series': []});
      final api = ApiClient(
        dio: Dio(BaseOptions(baseUrl: 'https://example.test'))
          ..httpClientAdapter = adapter,
        tokenProvider: () => testSession.token,
      );

      await tester.pumpWidget(
        ProviderScope(
          overrides: [
            sessionProvider.overrideWith((ref) => FakeSessionController(ref)),
            apiClientProvider.overrideWithValue(api),
            invoiceDraftsProvider.overrideWith((ref) async => []),
          ],
          child: const MaterialApp(home: InvoicingScreen()),
        ),
      );
      await tester.pumpAndSettle();

      expect(tester.takeException(), isNull);
    });

    testWidgets('no desborda en ancho de escritorio/web', (tester) async {
      tester.view.physicalSize = const Size(1440, 900);
      tester.view.devicePixelRatio = 1.0;
      addTearDown(tester.view.resetPhysicalSize);
      addTearDown(tester.view.resetDevicePixelRatio);

      final adapter = JsonAdapter({'enabled': true, 'fiscal_year': 2026, 'series': []});
      final api = ApiClient(
        dio: Dio(BaseOptions(baseUrl: 'https://example.test'))
          ..httpClientAdapter = adapter,
        tokenProvider: () => testSession.token,
      );

      await tester.pumpWidget(
        ProviderScope(
          overrides: [
            sessionProvider.overrideWith((ref) => FakeSessionController(ref)),
            apiClientProvider.overrideWithValue(api),
            invoiceDraftsProvider.overrideWith((ref) async => []),
          ],
          child: const MaterialApp(home: InvoicingScreen()),
        ),
      );
      await tester.pumpAndSettle();

      expect(tester.takeException(), isNull);
    });
  });
}

/// Adapter que devuelve bytes binarios fijos para cualquier peticion
/// (simula la descarga del PDF).
class _BytesAdapter implements HttpClientAdapter {
  _BytesAdapter(this.bytes);
  final Uint8List bytes;
  String? lastPath;

  @override
  Future<ResponseBody> fetch(
    RequestOptions options,
    Stream<Uint8List>? requestStream,
    Future<void>? cancelFuture,
  ) async {
    lastPath = options.path;
    return ResponseBody.fromBytes(bytes, 200);
  }

  @override
  void close({bool force = false}) {}
}
