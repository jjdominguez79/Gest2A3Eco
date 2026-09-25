import 'dart:typed_data';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:gestinem/core/api/api_client.dart';
import 'package:gestinem/features/documents/data/documents_repository.dart';
import 'package:gestinem/features/documents/domain/client_document.dart';
import 'package:gestinem/features/documents/presentation/document_preview_screen.dart';
import 'package:gestinem/features/documents/presentation/documents_providers.dart';
import 'package:pdfx/pdfx.dart';

void main() {
  testWidgets('fallo del visor permite guardar y reintentar el mismo PDF', (
    tester,
  ) async {
    var aperturas = 0;
    Future<PdfDocument> abrirDocumento(Uint8List _) async {
      aperturas++;
      throw Exception('No se pudo abrir el PDF');
    }

    final repository = _DocumentsRepository();
    await tester.pumpWidget(
      ProviderScope(
        overrides: [documentsRepositoryProvider.overrideWithValue(repository)],
        child: MaterialApp(
          home: DocumentPreviewScreen(
            documentId: 'document-1',
            abrirDocumento: abrirDocumento,
          ),
        ),
      ),
    );
    await tester.pumpAndSettle();

    expect(
      find.textContaining('No hace falta pedir otro certificado'),
      findsOneWidget,
    );
    expect(find.widgetWithText(FilledButton, 'Guardar PDF'), findsOneWidget);
    expect(repository.descargas, 1);
    expect(aperturas, 1);
    await tester.tap(find.text('Reintentar'));
    await tester.pumpAndSettle();
    expect(repository.descargas, 2);
    expect(aperturas, 2);
    expect(
      find.textContaining('No hace falta pedir otro certificado'),
      findsOneWidget,
    );
    // La copia entregada al visor no debe modificar el buffer del proveedor.
    expect(repository.bytes, orderedEquals([37, 80, 68, 70]));
  });

  testWidgets(
    'fallo de descarga permite volver a descargar sin nueva solicitud',
    (tester) async {
      final repository = _DocumentsRepository()..fallarDescarga = true;
      await tester.pumpWidget(
        ProviderScope(
          overrides: [
            documentsRepositoryProvider.overrideWithValue(repository),
          ],
          child: const MaterialApp(
            home: DocumentPreviewScreen(documentId: 'document-1'),
          ),
        ),
      );
      await tester.pumpAndSettle();
      expect(
        find.textContaining('No se pudo cargar la previsualizacion'),
        findsOneWidget,
      );
      expect(find.byTooltip('Guardar PDF'), findsOneWidget);
      await tester.tap(find.text('Reintentar'));
      await tester.pumpAndSettle();
      expect(repository.descargas, 2);
      expect(
        find.textContaining('No se pudo cargar la previsualizacion'),
        findsOneWidget,
      );
    },
  );
}

class _DocumentsRepository extends DocumentsRepository {
  _DocumentsRepository() : super(ApiClient(tokenProvider: () => null));

  int descargas = 0;
  bool fallarDescarga = false;
  final bytes = Uint8List.fromList([37, 80, 68, 70]);

  @override
  Future<Uint8List> downloadDocument(String id) async {
    expect(id, 'document-1');
    descargas++;
    if (fallarDescarga) throw Exception('Descarga fallida');
    return bytes;
  }

  @override
  Future<ClientDocument> getDocument(String id) async => const ClientDocument(
    id: 'document-1',
    documentType: 'certificate',
    displayName: 'Certificado AEAT',
    fileName: 'certificado.pdf',
    status: 'published',
  );
}
