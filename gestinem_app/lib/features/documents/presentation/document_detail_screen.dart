import 'package:file_picker/file_picker.dart';
import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:open_filex/open_filex.dart';
import 'package:share_plus/share_plus.dart';

import '../../../core/api/api_client.dart';
import '../domain/client_document.dart';
import 'documents_providers.dart';

/// Pantalla de detalle de un documento con descarga y compartir.
class DocumentDetailScreen extends ConsumerStatefulWidget {
  const DocumentDetailScreen({super.key, required this.documentId});

  final String documentId;

  @override
  ConsumerState<DocumentDetailScreen> createState() =>
      _DocumentDetailScreenState();
}

class _DocumentDetailScreenState extends ConsumerState<DocumentDetailScreen> {
  bool _downloading = false;

  @override
  Widget build(BuildContext context) {
    final docAsync = ref.watch(documentDetailProvider(widget.documentId));
    // Es una operacion independiente: si falla, el documento sigue siendo
    // consultable y se intentara marcar de nuevo en la proxima apertura.
    ref.watch(documentReadProvider(widget.documentId));

    return Scaffold(
      appBar: AppBar(title: const Text('Detalle del documento')),
      body: docAsync.when(
        loading: () => const Center(child: CircularProgressIndicator()),
        error: (error, _) => Center(child: Text('Error: $error')),
        data: (doc) {
          final theme = Theme.of(context);
          return ListView(
            padding: const EdgeInsets.all(16),
            children: [
              Card(
                child: Padding(
                  padding: const EdgeInsets.all(16),
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(doc.displayName, style: theme.textTheme.titleLarge),
                      const SizedBox(height: 8),
                      if (doc.documentDate != null)
                        _Row('Fecha', doc.documentDate!.substring(0, 10)),
                      if (doc.amount != null)
                        _Row('Importe', '${doc.amount} ${doc.currency}'),
                      _Row('Ejercicio', '${doc.fiscalYear}'),
                      _Row('Estado', _statusLabel(doc.status)),
                      if (doc.description != null &&
                          doc.description!.isNotEmpty)
                        _Row('Descripcion', doc.description!),
                    ],
                  ),
                ),
              ),
              if (doc.isReplaced) ...[
                const SizedBox(height: 8),
                Card(
                  color: Colors.orange.shade50,
                  child: ListTile(
                    leading: const Icon(Icons.warning, color: Colors.orange),
                    title: const Text('Este documento ha sido sustituido'),
                    subtitle: const Text('Existe una version mas reciente.'),
                    trailing: doc.replacedById != null
                        ? TextButton(
                            onPressed: () =>
                                context.push('/documents/${doc.replacedById}'),
                            child: const Text('Ver nueva'),
                          )
                        : null,
                  ),
                ),
              ],
              if (doc.isWithdrawn) ...[
                const SizedBox(height: 8),
                Card(
                  color: Colors.red.shade50,
                  child: ListTile(
                    leading: const Icon(Icons.block, color: Colors.red),
                    title: const Text('Documento retirado'),
                    subtitle: Text(
                      doc.withdrawalReason ?? 'No se puede descargar.',
                    ),
                  ),
                ),
              ],
              const SizedBox(height: 16),
              if (doc.isPublished || doc.isReplaced)
                Wrap(
                  spacing: 10,
                  runSpacing: 10,
                  children: [
                    ElevatedButton.icon(
                      onPressed: _downloading
                          ? null
                          : () => context.push(
                              '/documents/${widget.documentId}/preview',
                            ),
                      icon: const Icon(Icons.visibility_outlined),
                      label: const Text('Previsualizar'),
                    ),
                    ElevatedButton.icon(
                      onPressed: _downloading ? null : () => _download(doc),
                      icon: _downloading
                          ? const SizedBox(
                              width: 16,
                              height: 16,
                              child: CircularProgressIndicator(strokeWidth: 2),
                            )
                          : const Icon(Icons.download),
                      label: const Text('Guardar PDF'),
                    ),
                    OutlinedButton.icon(
                      onPressed: _downloading ? null : () => _share(doc),
                      icon: const Icon(Icons.share_outlined),
                      label: const Text('Compartir'),
                    ),
                  ],
                ),
            ],
          );
        },
      ),
    );
  }

  String _statusLabel(String status) {
    switch (status) {
      case 'published':
        return 'Publicado';
      case 'replaced':
        return 'Sustituido';
      case 'withdrawn':
        return 'Retirado';
      default:
        return status;
    }
  }

  Future<void> _download(ClientDocument doc) async {
    setState(() => _downloading = true);
    try {
      final repo = ref.read(documentsRepositoryProvider);
      final bytes = await repo.downloadDocument(widget.documentId);
      final uri = await FilePicker.saveFile(
        dialogTitle: 'Guardar factura',
        fileName: doc.fileName,
        bytes: bytes,
      );
      if (uri == null) return;
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(content: Text('PDF guardado correctamente')),
        );
      }
      if (!kIsWeb && uri.scheme == 'file') {
        await OpenFilex.open(uri.toFilePath());
      }
    } catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(
          context,
        ).showSnackBar(SnackBar(content: Text('Error: ${apiErrorMessage(e)}')));
      }
    } finally {
      if (mounted) setState(() => _downloading = false);
    }
  }

  Future<void> _share(ClientDocument doc) async {
    setState(() => _downloading = true);
    try {
      final bytes = await ref
          .read(documentsRepositoryProvider)
          .downloadDocument(widget.documentId);
      await SharePlus.instance.share(
        ShareParams(
          text: doc.displayName,
          files: [
            XFile.fromData(
              bytes,
              mimeType: 'application/pdf',
              name: doc.fileName,
            ),
          ],
        ),
      );
    } catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(
          context,
        ).showSnackBar(SnackBar(content: Text('Error: ${apiErrorMessage(e)}')));
      }
    } finally {
      if (mounted) setState(() => _downloading = false);
    }
  }
}

class _Row extends StatelessWidget {
  const _Row(this.label, this.value);

  final String label;
  final String value;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 4),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          SizedBox(
            width: 100,
            child: Text(
              label,
              style: Theme.of(context).textTheme.bodySmall?.copyWith(
                color: Theme.of(context).colorScheme.onSurfaceVariant,
              ),
            ),
          ),
          Expanded(child: Text(value)),
        ],
      ),
    );
  }
}
