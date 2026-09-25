import 'dart:typed_data';

import 'package:file_picker/file_picker.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:pdfx/pdfx.dart';

import '../../../core/api/api_client.dart';
import 'documents_providers.dart';

typedef AbrirDocumentoPdf = Future<PdfDocument> Function(Uint8List datos);

class DocumentPreviewScreen extends ConsumerStatefulWidget {
  const DocumentPreviewScreen({
    super.key,
    required this.documentId,
    this.abrirDocumento,
  });

  final String documentId;
  final AbrirDocumentoPdf? abrirDocumento;

  @override
  ConsumerState<DocumentPreviewScreen> createState() =>
      _DocumentPreviewScreenState();
}

class _DocumentPreviewScreenState extends ConsumerState<DocumentPreviewScreen> {
  int _previewAttempt = 0;
  bool _saving = false;

  void _retry() {
    setState(() => _previewAttempt++);
    ref.invalidate(documentBytesProvider(widget.documentId));
  }

  Future<void> _savePdf() async {
    if (_saving) return;
    setState(() => _saving = true);
    try {
      // Descargar otra copia: PDF.js puede transferir el buffer al worker.
      final bytes = await ref
          .read(documentsRepositoryProvider)
          .downloadDocument(widget.documentId);
      final document = ref.read(documentDetailProvider(widget.documentId));
      await FilePicker.saveFile(
        dialogTitle: 'Guardar PDF',
        fileName: document.valueOrNull?.fileName ?? 'documento.pdf',
        bytes: bytes,
      );
    } catch (error) {
      if (mounted) {
        ScaffoldMessenger.of(
          context,
        ).showSnackBar(SnackBar(content: Text(apiErrorMessage(error))));
      }
    } finally {
      if (mounted) setState(() => _saving = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final document = ref.watch(documentDetailProvider(widget.documentId));
    final bytes = ref.watch(documentBytesProvider(widget.documentId));

    return Scaffold(
      appBar: AppBar(
        title: Text(
          document.valueOrNull?.displayName ?? 'Previsualizar documento',
        ),
        actions: [
          IconButton(
            tooltip: 'Guardar PDF',
            onPressed: _saving ? null : _savePdf,
            icon: const Icon(Icons.download),
          ),
        ],
      ),
      body: bytes.when(
        skipLoadingOnRefresh: false,
        loading: () => const Center(child: CircularProgressIndicator()),
        error: (error, _) => Center(
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              const Icon(Icons.picture_as_pdf_outlined, size: 48),
              const SizedBox(height: 12),
              Text(
                'No se pudo cargar la previsualizacion. ${apiErrorMessage(error)}',
              ),
              const SizedBox(height: 12),
              FilledButton(onPressed: _retry, child: const Text('Reintentar')),
            ],
          ),
        ),
        data: (data) => PdfBytesPreview(
          key: ValueKey(_previewAttempt),
          data: data,
          onRetry: _retry,
          onSave: _saving ? null : _savePdf,
          abrirDocumento: widget.abrirDocumento,
        ),
      ),
    );
  }
}

class PdfBytesPreview extends StatefulWidget {
  const PdfBytesPreview({
    super.key,
    required this.data,
    required this.onRetry,
    this.onSave,
    this.abrirDocumento,
  });

  final Uint8List data;
  final VoidCallback onRetry;
  final VoidCallback? onSave;
  final AbrirDocumentoPdf? abrirDocumento;

  @override
  State<PdfBytesPreview> createState() => _PdfBytesPreviewState();
}

class _PdfBytesPreviewState extends State<PdfBytesPreview> {
  late final PdfController _controller = PdfController(
    document:
        widget.abrirDocumento?.call(Uint8List.fromList(widget.data)) ??
        PdfDocument.openData(Uint8List.fromList(widget.data)),
  );

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return ColoredBox(
      color: const Color(0xFFE6EAED),
      child: PdfView(
        controller: _controller,
        scrollDirection: Axis.vertical,
        builders: PdfViewBuilders<DefaultBuilderOptions>(
          options: const DefaultBuilderOptions(),
          documentLoaderBuilder: (_) =>
              const Center(child: CircularProgressIndicator()),
          pageLoaderBuilder: (_) =>
              const Center(child: CircularProgressIndicator()),
          errorBuilder: (_, error) => Center(
            child: Padding(
              padding: const EdgeInsets.all(24),
              child: Column(
                mainAxisSize: MainAxisSize.min,
                children: [
                  const Text(
                    'No se pudo mostrar el PDF en este navegador. '
                    'Puedes reintentar o guardar el archivo para abrirlo '
                    'con un lector PDF. No hace falta pedir otro certificado.',
                    textAlign: TextAlign.center,
                  ),
                  const SizedBox(height: 16),
                  Wrap(
                    spacing: 12,
                    children: [
                      OutlinedButton(
                        onPressed: widget.onRetry,
                        child: const Text('Reintentar'),
                      ),
                      FilledButton.icon(
                        onPressed: widget.onSave,
                        icon: const Icon(Icons.download),
                        label: const Text('Guardar PDF'),
                      ),
                    ],
                  ),
                ],
              ),
            ),
          ),
        ),
      ),
    );
  }
}
