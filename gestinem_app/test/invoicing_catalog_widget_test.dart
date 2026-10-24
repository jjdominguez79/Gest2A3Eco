import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:gestinem/features/auth/presentation/auth_controller.dart';
import 'package:gestinem/features/invoicing/domain/client_invoice.dart';
import 'package:gestinem/features/invoicing/presentation/catalog_list_screen.dart';
import 'package:gestinem/features/invoicing/presentation/invoicing_providers.dart';

import 'test_helpers.dart';

void main() {
  group('CatalogListScreen', () {
    testWidgets('muestra mensaje vacio sin articulos', (tester) async {
      await tester.pumpWidget(
        ProviderScope(
          overrides: [
            sessionProvider.overrideWith((ref) => FakeSessionController(ref)),
            catalogItemsProvider.overrideWith((ref) async => []),
          ],
          child: const MaterialApp(home: CatalogListScreen()),
        ),
      );
      await tester.pumpAndSettle();

      expect(find.text('No hay productos ni servicios todavia.'), findsOneWidget);
    });

    testWidgets('muestra articulos del catalogo con precio e IVA', (
      tester,
    ) async {
      final items = [
        const CatalogItem(
          id: 'cat-1',
          itemType: 'service',
          description: 'Hora de consultoria',
          unitPrice: '80.00',
          vatRate: '21.00',
        ),
        const CatalogItem(
          id: 'cat-2',
          itemType: 'product',
          description: 'Licencia software',
          unitPrice: '199.00',
          vatRate: '21.00',
        ),
      ];

      await tester.pumpWidget(
        ProviderScope(
          overrides: [
            sessionProvider.overrideWith((ref) => FakeSessionController(ref)),
            catalogItemsProvider.overrideWith((ref) async => items),
          ],
          child: const MaterialApp(home: CatalogListScreen()),
        ),
      );
      await tester.pumpAndSettle();

      expect(find.text('Hora de consultoria'), findsOneWidget);
      expect(find.text('Licencia software'), findsOneWidget);
      expect(find.textContaining('80.00'), findsOneWidget);
      expect(find.byIcon(Icons.handyman_outlined), findsOneWidget);
      expect(find.byIcon(Icons.inventory_2_outlined), findsOneWidget);
    });

    testWidgets('error muestra boton de reintentar', (tester) async {
      await tester.pumpWidget(
        ProviderScope(
          overrides: [
            sessionProvider.overrideWith((ref) => FakeSessionController(ref)),
            catalogItemsProvider.overrideWith(
              (ref) async => throw Exception('fallo de red'),
            ),
          ],
          child: const MaterialApp(home: CatalogListScreen()),
        ),
      );
      await tester.pumpAndSettle();

      expect(find.text('Reintentar'), findsOneWidget);
    });
  });
}
