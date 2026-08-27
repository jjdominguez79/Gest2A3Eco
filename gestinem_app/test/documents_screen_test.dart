import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:gestinem/features/auth/presentation/auth_controller.dart';
import 'package:gestinem/features/documents/domain/client_document.dart';
import 'package:gestinem/features/documents/presentation/documents_providers.dart';
import 'package:gestinem/features/documents/presentation/documents_screen.dart';
import 'package:gestinem/features/platform/features_provider.dart';

import 'test_helpers.dart';

void main() {
  group('DocumentsScreen - feature gate', () {
    testWidgets('muestra mensaje cuando documents esta desactivado', (
      tester,
    ) async {
      await tester.pumpWidget(
        ProviderScope(
          overrides: [
            sessionProvider.overrideWith(
              (ref) => FakeSessionController(ref),
            ),
            platformFeaturesProvider.overrideWith(
              (ref) async => const PlatformFeatures(documents: false),
            ),
            documentsProvider.overrideWith(
              (ref) async =>
                  const DocumentListResponse(items: [], total: 0),
            ),
          ],
          child: const MaterialApp(home: DocumentsScreen()),
        ),
      );
      await tester.pumpAndSettle();

      expect(
        find.text('El area documental no esta habilitada.'),
        findsOneWidget,
      );
      expect(find.byType(ListView), findsNothing);
    });

    testWidgets('muestra listado cuando documents esta activado', (
      tester,
    ) async {
      final docs = DocumentListResponse(
        items: [
          ClientDocument(
            id: 'doc-1',
            documentType: 'factura',
            displayName: 'Factura 001',
            fileName: 'factura_001.pdf',
            status: 'published',
            isRead: false,
            documentDate: '2026-03-15',
            amount: '1200.00',
          ),
        ],
        total: 1,
      );

      await tester.pumpWidget(
        ProviderScope(
          overrides: [
            sessionProvider.overrideWith(
              (ref) => FakeSessionController(ref),
            ),
            platformFeaturesProvider.overrideWith(
              (ref) async =>
                  const PlatformFeatures(documents: true),
            ),
            documentsProvider.overrideWith((ref) async => docs),
          ],
          child: const MaterialApp(home: DocumentsScreen()),
        ),
      );
      await tester.pumpAndSettle();

      expect(find.text('Factura 001'), findsOneWidget);
      expect(find.textContaining('1200.00'), findsOneWidget);
    });
  });

  group('DocumentsScreen - listado', () {
    testWidgets('muestra mensaje vacio si no hay documentos', (tester) async {
      await tester.pumpWidget(
        ProviderScope(
          overrides: [
            sessionProvider.overrideWith(
              (ref) => FakeSessionController(ref),
            ),
            platformFeaturesProvider.overrideWith(
              (ref) async =>
                  const PlatformFeatures(documents: true),
            ),
            documentsProvider.overrideWith(
              (ref) async =>
                  const DocumentListResponse(items: [], total: 0),
            ),
          ],
          child: const MaterialApp(home: DocumentsScreen()),
        ),
      );
      await tester.pumpAndSettle();

      expect(
        find.text('No hay documentos para este ejercicio.'),
        findsOneWidget,
      );
    });

    testWidgets('documento no leido se muestra en negrita', (tester) async {
      final docs = DocumentListResponse(
        items: [
          ClientDocument(
            id: 'doc-unread',
            documentType: 'factura',
            displayName: 'Factura sin leer',
            fileName: 'f.pdf',
            status: 'published',
            isRead: false,
          ),
          ClientDocument(
            id: 'doc-read',
            documentType: 'factura',
            displayName: 'Factura leida',
            fileName: 'g.pdf',
            status: 'published',
            isRead: true,
          ),
        ],
        total: 2,
      );

      await tester.pumpWidget(
        ProviderScope(
          overrides: [
            sessionProvider.overrideWith(
              (ref) => FakeSessionController(ref),
            ),
            platformFeaturesProvider.overrideWith(
              (ref) async =>
                  const PlatformFeatures(documents: true),
            ),
            documentsProvider.overrideWith((ref) async => docs),
          ],
          child: const MaterialApp(home: DocumentsScreen()),
        ),
      );
      await tester.pumpAndSettle();

      expect(find.text('Factura sin leer'), findsOneWidget);
      expect(find.text('Factura leida'), findsOneWidget);

      // El no leido tiene fontWeight.bold
      final unreadText = tester.widget<Text>(find.text('Factura sin leer'));
      expect(unreadText.style?.fontWeight, FontWeight.bold);

      // El leido no tiene negrita forzada
      final readText = tester.widget<Text>(find.text('Factura leida'));
      expect(readText.style?.fontWeight, isNot(FontWeight.bold));
    });

    testWidgets('documento retirado muestra icono block y texto Retirada', (
      tester,
    ) async {
      final docs = DocumentListResponse(
        items: [
          ClientDocument(
            id: 'doc-withdrawn',
            documentType: 'factura',
            displayName: 'Factura retirada',
            fileName: 'r.pdf',
            status: 'withdrawn',
          ),
        ],
        total: 1,
      );

      await tester.pumpWidget(
        ProviderScope(
          overrides: [
            sessionProvider.overrideWith(
              (ref) => FakeSessionController(ref),
            ),
            platformFeaturesProvider.overrideWith(
              (ref) async =>
                  const PlatformFeatures(documents: true),
            ),
            documentsProvider.overrideWith((ref) async => docs),
          ],
          child: const MaterialApp(home: DocumentsScreen()),
        ),
      );
      await tester.pumpAndSettle();

      expect(find.byIcon(Icons.block), findsOneWidget);
      expect(find.textContaining('Retirada'), findsOneWidget);
    });

    testWidgets('documento sustituido muestra icono swap y texto Sustituida', (
      tester,
    ) async {
      final docs = DocumentListResponse(
        items: [
          ClientDocument(
            id: 'doc-replaced',
            documentType: 'factura',
            displayName: 'Factura sustituida',
            fileName: 's.pdf',
            status: 'replaced',
            replacedById: 'doc-new',
          ),
        ],
        total: 1,
      );

      await tester.pumpWidget(
        ProviderScope(
          overrides: [
            sessionProvider.overrideWith(
              (ref) => FakeSessionController(ref),
            ),
            platformFeaturesProvider.overrideWith(
              (ref) async =>
                  const PlatformFeatures(documents: true),
            ),
            documentsProvider.overrideWith((ref) async => docs),
          ],
          child: const MaterialApp(home: DocumentsScreen()),
        ),
      );
      await tester.pumpAndSettle();

      expect(find.byIcon(Icons.swap_horiz), findsOneWidget);
      expect(find.textContaining('Sustituida'), findsOneWidget);
    });
  });

  group('DocumentsScreen - selector de ejercicio', () {
    testWidgets('muestra boton de calendario y opciones de ejercicio', (
      tester,
    ) async {
      await tester.pumpWidget(
        ProviderScope(
          overrides: [
            sessionProvider.overrideWith(
              (ref) => FakeSessionController(ref),
            ),
            platformFeaturesProvider.overrideWith(
              (ref) async =>
                  const PlatformFeatures(documents: true),
            ),
            documentsProvider.overrideWith(
              (ref) async =>
                  const DocumentListResponse(items: [], total: 0),
            ),
          ],
          child: const MaterialApp(home: DocumentsScreen()),
        ),
      );
      await tester.pumpAndSettle();

      expect(find.byIcon(Icons.calendar_today), findsOneWidget);

      await tester.tap(find.byIcon(Icons.calendar_today));
      await tester.pumpAndSettle();

      final currentYear = DateTime.now().year;
      for (var y = currentYear; y >= currentYear - 4; y--) {
        expect(find.textContaining('$y'), findsWidgets);
      }
    });
  });
}
