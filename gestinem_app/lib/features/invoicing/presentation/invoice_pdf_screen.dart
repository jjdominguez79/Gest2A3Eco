import 'package:file_picker/file_picker.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../core/api/api_client.dart';
import '../../documents/presentation/document_preview_screen.dart';
import 'invoicing_providers.dart';

/// Visualiza y permite descargar el PDF de una factura emitida.
class InvoicePdfScreen extends ConsumerStatefulWidget {
  const InvoicePdfScreen({super.key, required this.invoiceId});

  final String invoiceId;

  @override
  ConsumerState<InvoicePdfScreen> createState() => _InvoicePdfScreenState();
}

class _InvoicePdfScreenState extends ConsumerState<InvoicePdfScreen> {
  int _attempt = 0;
  bool _saving = false;

  void _retry() {
    setState(() => _attempt++);
    ref.invalidate(invoicePdfBytesProvider(widget.invoiceId));
  }

  Future<void> _save() async {
    if (_saving) return;
    setState(() => _saving = true);
    try {
      final bytes = await ref
          .read(invoicingRepositoryProvider)
          .downloadInvoicePdf(widget.invoiceId);
      final invoice = ref.read(invoiceDetailProvider(widget.invoiceId));
      final fileName = invoice.valueOrNull != null
          ? '${invoice.valueOrNull!.displayNumber}.pdf'
          : 'factura.pdf';
      await FilePicker.saveFile(
        dialogTitle: 'Guardar factura',
        fileName: fileName,
        bytes: bytes,
      );
    } catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(
          context,
        ).showSnackBar(SnackBar(content: Text(apiErrorMessage(e))));
      }
    } finally {
      if (mounted) setState(() => _saving = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final bytes = ref.watch(invoicePdfBytesProvider(widget.invoiceId));

    return Scaffold(
      appBar: AppBar(
        title: const Text('Factura (PDF)'),
        actions: [
          IconButton(
            tooltip: 'Guardar PDF',
            onPressed: _saving ? null : _save,
            icon: const Icon(Icons.download),
          ),
        ],
      ),
      body: bytes.when(
        skipLoadingOnRefresh: false,
        loading: () => const Center(child: CircularProgressIndicator()),
        error: (error, _) => Center(
          child: Padding(
            padding: const EdgeInsets.all(24),
            child: Column(
              mainAxisSize: MainAxisSize.min,
              children: [
                const Icon(Icons.picture_as_pdf_outlined, size: 48),
                const SizedBox(height: 12),
                Text(
                  'No se pudo cargar el PDF. ${apiErrorMessage(error)}',
                  textAlign: TextAlign.center,
                ),
                const SizedBox(height: 12),
                FilledButton(
                  onPressed: _retry,
                  child: const Text('Reintentar'),
                ),
              ],
            ),
          ),
        ),
        data: (data) => PdfBytesPreview(
          key: ValueKey(_attempt),
          data: data,
          onRetry: _retry,
          onSave: _saving ? null : _save,
        ),
      ),
    );
  }
}
