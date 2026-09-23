import 'dart:typed_data';

import 'package:file_picker/file_picker.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../core/api/api_client.dart';
import '../../documents/presentation/document_preview_screen.dart';
import 'certificates_providers.dart';

class StaffCertificatePreviewScreen extends ConsumerStatefulWidget {
  const StaffCertificatePreviewScreen({
    super.key,
    required this.companyCode,
    required this.requestId,
    required this.documentName,
    this.receipt = false,
  });

  final String companyCode;
  final String requestId;
  final String documentName;
  final bool receipt;

  @override
  ConsumerState<StaffCertificatePreviewScreen> createState() =>
      _StaffCertificatePreviewScreenState();
}

class _StaffCertificatePreviewScreenState
    extends ConsumerState<StaffCertificatePreviewScreen> {
  int _attempt = 0;
  bool _saving = false;

  StaffCertificateDocumentQuery get _query => (
    companyCode: widget.companyCode,
    requestId: widget.requestId,
    receipt: widget.receipt,
  );

  Future<Uint8List> _download() => ref
      .read(certificatesRepositoryProvider)
      .downloadRequestDocument(
        widget.requestId,
        companyCode: widget.companyCode,
        receipt: widget.receipt,
      );

  void _retry() {
    setState(() => _attempt++);
    ref.invalidate(staffCertificateDocumentProvider(_query));
  }

  Future<void> _save() async {
    if (_saving) return;
    setState(() => _saving = true);
    try {
      final bytes = await _download();
      await FilePicker.saveFile(
        dialogTitle: 'Guardar PDF',
        fileName: _fileName,
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

  String get _fileName {
    final safe = widget.documentName
        .replaceAll(RegExp(r'[^A-Za-z0-9._-]+'), '-')
        .replaceAll(RegExp(r'^-+|-+$'), '');
    return '${safe.isEmpty ? 'certificado' : safe}.pdf';
  }

  @override
  Widget build(BuildContext context) {
    final bytes = ref.watch(staffCertificateDocumentProvider(_query));
    return Scaffold(
      appBar: AppBar(
        title: Text(widget.receipt ? 'Resguardo' : widget.documentName),
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
              FilledButton(onPressed: _retry, child: const Text('Reintentar')),
            ],
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
