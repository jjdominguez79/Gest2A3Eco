import 'dart:async';
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
import 'package:pdfx/src/renderer/interfaces/platform.dart';

void main() {
  testWidgets('fallo del visor permite guardar y reintentar el mismo PDF', (
    tester,
  ) async {
    // pdfx usa Pigeon en macOS/iOS y MethodChannel en Windows: simular la
    // plataforma evita depender del canal nativo elegido por cada sistema.
    final plataformaAnterior = PdfxPlatform.instance;
    final visor = _PdfxPlatformConError();
    PdfxPlatform.instance = visor;
    addTearDown(() => PdfxPlatform.instance = plataformaAnterior);
    final repository = _DocumentsRepository();
    await tester.pumpWidget(
      ProviderScope(
        overrides: [documentsRepositoryProvider.overrideWithValue(repository)],
        child: const MaterialApp(
          home: DocumentPreviewScreen(documentId: 'document-1'),
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
    expect(visor.aperturas, 1);
    await tester.tap(find.text('Reintentar'));
    await tester.pumpAndSettle();
    expect(repository.descargas, 2);
    expect(visor.aperturas, 2);
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

class _PdfxPlatformConError extends PdfxPlatform {
  int aperturas = 0;

  @override
  Future<PdfDocument> openData(
    FutureOr<Uint8List> data, {
    String? password,
  }) async {
    aperturas++;
    throw Exception('No se pudo abrir el PDF');
  }

  @override
  Future<PdfDocument> openAsset(String name, {String? password}) =>
      throw UnimplementedError();

  @override
  Future<PdfDocument> openFile(String filePath, {String? password}) =>
      throw UnimplementedError();
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
