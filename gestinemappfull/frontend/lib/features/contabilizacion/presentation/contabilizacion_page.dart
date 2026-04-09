import 'dart:io';

import 'package:file_picker/file_picker.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../core/models/accounting_models.dart';
import '../application/accounting_controller.dart';

class ContabilizacionPage extends ConsumerWidget {
  const ContabilizacionPage({
    super.key,
    required this.token,
    required this.companyId,
    required this.companyName,
  });

  final String token;
  final String companyId;
  final String companyName;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final scope = AccountingScope(
      token: token,
      companyId: companyId,
      companyName: companyName,
    );
    final state = ref.watch(accountingControllerProvider(scope));
    final controller = ref.read(accountingControllerProvider(scope).notifier);

    return Container(
      decoration: BoxDecoration(
        color: const Color(0xFFF5F7FA),
        borderRadius: BorderRadius.circular(18),
      ),
      child: state.isLoading
          ? const Center(child: CircularProgressIndicator())
          : Row(
              children: [
                Expanded(
                  flex: 6,
                  child: _PendingPanel(
                    state: state,
                    companyName: companyName,
                    onToggleSelection: controller.toggleDocumentSelection,
                    onGenerate: () => _generateBatch(context, controller),
                  ),
                ),
                const VerticalDivider(width: 1),
                Expanded(
                  flex: 7,
                  child: _BatchesPanel(
                    state: state,
                    onOpenBatch: controller.openBatch,
                    onStatusFilterChanged: controller.setStatusFilter,
                    onPickDateFrom: () => _pickDate(
                      context,
                      initialDate: state.dateFrom,
                      onSelected: (value) =>
                          controller.setDateRange(value, state.dateTo),
                    ),
                    onPickDateTo: () => _pickDate(
                      context,
                      initialDate: state.dateTo,
                      onSelected: (value) =>
                          controller.setDateRange(state.dateFrom, value),
                    ),
                    onClearDates: () => controller.setDateRange(null, null),
                    onDownload: () => _downloadBatch(context, controller),
                    onMarkExported: () =>
                        _markBatchExported(context, controller, state),
                  ),
                ),
              ],
            ),
    );
  }

  Future<void> _generateBatch(
    BuildContext context,
    AccountingController controller,
  ) async {
    final notes = await _askNotes(
      context,
      title: 'Notas del lote',
      confirmLabel: 'Generar lote',
    );
    if (notes == null) {
      return;
    }
    final batch = await controller.generateBatchFromSelection(notes: notes);
    if (batch == null || !context.mounted) {
      return;
    }
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(
        content: Text(
          'Lote ${batch.fileName ?? batch.id} generado con ${batch.totalDocuments} documentos.',
        ),
      ),
    );
  }

  Future<void> _downloadBatch(
    BuildContext context,
    AccountingController controller,
  ) async {
    final file = await controller.downloadSelectedBatch();
    if (file == null || !context.mounted) {
      return;
    }
    final targetPath = await FilePicker.platform.saveFile(
      dialogTitle: 'Guardar suenlace.dat',
      fileName: file.filename,
    );
    if (targetPath == null) {
      return;
    }
    await File(targetPath).writeAsBytes(file.bytes);
    if (!context.mounted) {
      return;
    }
    ScaffoldMessenger.of(
      context,
    ).showSnackBar(SnackBar(content: Text('Archivo guardado en $targetPath')));
  }

  Future<void> _markBatchExported(
    BuildContext context,
    AccountingController controller,
    AccountingState state,
  ) async {
    final selectedBatch = state.selectedBatch;
    if (selectedBatch == null) {
      return;
    }
    if (selectedBatch.status == 'exported') {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(
          content: Text('Este lote ya fue marcado como exportado.'),
        ),
      );
      return;
    }
    final notes = await _askNotes(
      context,
      title: 'Marcar lote como exportado',
      confirmLabel: 'Marcar exportado',
    );
    if (notes == null) {
      return;
    }
    final batch = await controller.markSelectedBatchExported(notes: notes);
    if (batch == null || !context.mounted) {
      return;
    }
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(
        content: Text(
          'Lote ${batch.fileName ?? batch.id} marcado como exportado.',
        ),
      ),
    );
  }

  Future<void> _pickDate(
    BuildContext context, {
    required DateTime? initialDate,
    required ValueChanged<DateTime> onSelected,
  }) async {
    final now = DateTime.now();
    final picked = await showDatePicker(
      context: context,
      initialDate: initialDate ?? now,
      firstDate: DateTime(2020),
      lastDate: DateTime(now.year + 2),
    );
    if (picked != null) {
      onSelected(picked);
    }
  }

  Future<String?> _askNotes(
    BuildContext context, {
    required String title,
    required String confirmLabel,
  }) async {
    final controller = TextEditingController();
    final result = await showDialog<String>(
      context: context,
      builder: (context) {
        return AlertDialog(
          title: Text(title),
          content: TextField(
            controller: controller,
            minLines: 3,
            maxLines: 5,
            decoration: const InputDecoration(
              labelText: 'Notas (opcional)',
              hintText: 'Observaciones o referencia interna',
            ),
          ),
          actions: [
            TextButton(
              onPressed: () => Navigator.of(context).pop(null),
              child: const Text('Cancelar'),
            ),
            FilledButton(
              onPressed: () =>
                  Navigator.of(context).pop(controller.text.trim()),
              child: Text(confirmLabel),
            ),
          ],
        );
      },
    );
    controller.dispose();
    return result;
  }
}

class _PendingPanel extends StatelessWidget {
  const _PendingPanel({
    required this.state,
    required this.companyName,
    required this.onToggleSelection,
    required this.onGenerate,
  });

  final AccountingState state;
  final String companyName;
  final void Function(String documentId, bool value) onToggleSelection;
  final VoidCallback onGenerate;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.all(20),
      color: Colors.white,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    const Text(
                      'Pendientes de contabilizar',
                      style: TextStyle(
                        fontSize: 24,
                        fontWeight: FontWeight.w700,
                      ),
                    ),
                    const SizedBox(height: 8),
                    Text(
                      'Solo se listan documentos en pending_accounting. Empresa: $companyName.',
                    ),
                  ],
                ),
              ),
              FilledButton.icon(
                onPressed: state.isGenerating ? null : onGenerate,
                icon: state.isGenerating
                    ? const SizedBox(
                        width: 16,
                        height: 16,
                        child: CircularProgressIndicator(
                          strokeWidth: 2,
                          color: Colors.white,
                        ),
                      )
                    : const Icon(Icons.playlist_add_check_circle_rounded),
                label: const Text('Generar lote'),
              ),
            ],
          ),
          const SizedBox(height: 16),
          if (state.errorMessage != null)
            Padding(
              padding: const EdgeInsets.only(bottom: 12),
              child: Text(
                state.errorMessage!,
                style: const TextStyle(color: Colors.redAccent),
              ),
            ),
          Expanded(
            child: state.pendingItems.isEmpty
                ? const Center(
                    child: Text('No hay facturas pendientes de contabilizar.'),
                  )
                : ListView.separated(
                    itemCount: state.pendingItems.length,
                    separatorBuilder: (_, __) => const Divider(height: 1),
                    itemBuilder: (context, index) {
                      final item = state.pendingItems[index];
                      final selected = state.selectedDocumentIds.contains(
                        item.documentId,
                      );
                      return CheckboxListTile(
                        value: selected,
                        onChanged: (value) =>
                            onToggleSelection(item.documentId, value ?? false),
                        title: Text(item.originalFilename),
                        subtitle: Text(
                          '${item.invoiceNumber ?? 'Sin numero'} · ${item.supplierName ?? 'Proveedor'} · ${item.companyAccountCode ?? 'Sin subcuenta'}',
                        ),
                        secondary: Column(
                          mainAxisAlignment: MainAxisAlignment.center,
                          crossAxisAlignment: CrossAxisAlignment.end,
                          children: [
                            if (item.totalAmount != null)
                              Text(item.totalAmount!.toStringAsFixed(2)),
                            Text(
                              _formatWorkflowStatus(item.workflowStatus),
                              style: const TextStyle(fontSize: 12),
                            ),
                          ],
                        ),
                        controlAffinity: ListTileControlAffinity.leading,
                      );
                    },
                  ),
          ),
        ],
      ),
    );
  }
}

class _BatchesPanel extends StatelessWidget {
  const _BatchesPanel({
    required this.state,
    required this.onOpenBatch,
    required this.onStatusFilterChanged,
    required this.onPickDateFrom,
    required this.onPickDateTo,
    required this.onClearDates,
    required this.onDownload,
    required this.onMarkExported,
  });

  final AccountingState state;
  final ValueChanged<String> onOpenBatch;
  final ValueChanged<String?> onStatusFilterChanged;
  final VoidCallback onPickDateFrom;
  final VoidCallback onPickDateTo;
  final VoidCallback onClearDates;
  final VoidCallback onDownload;
  final VoidCallback onMarkExported;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.all(20),
      color: const Color(0xFFFCFDFE),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              const Expanded(
                child: Text(
                  'Historico de lotes',
                  style: TextStyle(fontSize: 24, fontWeight: FontWeight.w700),
                ),
              ),
              OutlinedButton.icon(
                onPressed: state.selectedBatch == null || state.isDownloading
                    ? null
                    : onDownload,
                icon: state.isDownloading
                    ? const SizedBox(
                        width: 16,
                        height: 16,
                        child: CircularProgressIndicator(strokeWidth: 2),
                      )
                    : const Icon(Icons.download_rounded),
                label: const Text('Descargar .dat'),
              ),
              const SizedBox(width: 12),
              FilledButton.icon(
                onPressed:
                    state.selectedBatch == null || state.isMarkingExported
                    ? null
                    : onMarkExported,
                icon: state.isMarkingExported
                    ? const SizedBox(
                        width: 16,
                        height: 16,
                        child: CircularProgressIndicator(
                          strokeWidth: 2,
                          color: Colors.white,
                        ),
                      )
                    : const Icon(Icons.cloud_done_rounded),
                label: const Text('Marcar exportado'),
              ),
            ],
          ),
          const SizedBox(height: 16),
          Wrap(
            spacing: 12,
            runSpacing: 12,
            crossAxisAlignment: WrapCrossAlignment.center,
            children: [
              SizedBox(
                width: 220,
                child: DropdownButtonFormField<String?>(
                  initialValue: state.statusFilter,
                  decoration: const InputDecoration(
                    labelText: 'Estado lote',
                    border: OutlineInputBorder(),
                  ),
                  items: const [
                    DropdownMenuItem(value: null, child: Text('Todos')),
                    DropdownMenuItem(value: 'draft', child: Text('Borrador')),
                    DropdownMenuItem(
                      value: 'generated',
                      child: Text('Generado'),
                    ),
                    DropdownMenuItem(
                      value: 'downloaded',
                      child: Text('Descargado'),
                    ),
                    DropdownMenuItem(
                      value: 'exported',
                      child: Text('Exportado'),
                    ),
                    DropdownMenuItem(value: 'error', child: Text('Error')),
                  ],
                  onChanged: onStatusFilterChanged,
                ),
              ),
              OutlinedButton.icon(
                onPressed: onPickDateFrom,
                icon: const Icon(Icons.date_range_rounded),
                label: Text(
                  state.dateFrom == null
                      ? 'Desde'
                      : _formatDateShort(state.dateFrom!),
                ),
              ),
              OutlinedButton.icon(
                onPressed: onPickDateTo,
                icon: const Icon(Icons.event_rounded),
                label: Text(
                  state.dateTo == null
                      ? 'Hasta'
                      : _formatDateShort(state.dateTo!),
                ),
              ),
              TextButton(
                onPressed: onClearDates,
                child: const Text('Limpiar fechas'),
              ),
            ],
          ),
          const SizedBox(height: 16),
          Expanded(
            child: Row(
              children: [
                SizedBox(
                  width: 420,
                  child: state.batches.isEmpty
                      ? const Center(child: Text('Sin lotes generados.'))
                      : ListView.separated(
                          itemCount: state.batches.length,
                          separatorBuilder: (_, __) => const Divider(height: 1),
                          itemBuilder: (context, index) {
                            final batch = state.batches[index];
                            final selected =
                                state.selectedBatch?.id == batch.id;
                            return ListTile(
                              selected: selected,
                              selectedTileColor: const Color(0xFFEAF4FB),
                              onTap: () => onOpenBatch(batch.id),
                              title: Text(batch.fileName ?? batch.id),
                              subtitle: Text(
                                '${_formatBatchStatus(batch.status)} · ${batch.totalDocuments} docs · ${batch.totalEntries} entradas',
                              ),
                              trailing: Text(
                                batch.generatedAt == null
                                    ? _formatDateShort(batch.createdAt)
                                    : _formatDateShort(batch.generatedAt!),
                              ),
                            );
                          },
                        ),
                ),
                const VerticalDivider(width: 1),
                Expanded(
                  child: state.selectedBatch == null
                      ? const Center(child: Text('Selecciona un lote.'))
                      : _BatchDetail(batch: state.selectedBatch!),
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }
}

class _BatchDetail extends StatelessWidget {
  const _BatchDetail({required this.batch});

  final AccountingBatchModel batch;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.only(left: 20),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            batch.fileName ?? batch.id,
            style: const TextStyle(fontSize: 20, fontWeight: FontWeight.w700),
          ),
          const SizedBox(height: 8),
          Wrap(
            spacing: 12,
            runSpacing: 8,
            children: [
              _metaChip('Estado', _formatBatchStatus(batch.status)),
              _metaChip(
                'A3 snapshot',
                batch.a3CompanyCodeSnapshot ?? 'Sin codigo',
              ),
              _metaChip('Docs', '${batch.totalDocuments}'),
              _metaChip('Entradas', '${batch.totalEntries}'),
            ],
          ),
          const SizedBox(height: 16),
          _metaLine('Hash', batch.fileHash ?? 'No disponible'),
          _metaLine('Generado', _formatDateTime(batch.generatedAt)),
          _metaLine('Generado por', batch.generatedByName ?? '-'),
          _metaLine('Descargado', _formatDateTime(batch.downloadedAt)),
          _metaLine('Descargado por', batch.downloadedByName ?? '-'),
          _metaLine('Exportado', _formatDateTime(batch.exportedAt)),
          _metaLine('Exportado por', batch.exportedByName ?? '-'),
          _metaLine('Ruta', batch.filePath ?? '-'),
          if (batch.notes != null && batch.notes!.isNotEmpty)
            _metaLine('Notas', batch.notes!),
          if (batch.errorMessage != null) ...[
            const SizedBox(height: 8),
            Text(
              batch.errorMessage!,
              style: const TextStyle(color: Colors.redAccent),
            ),
          ],
          const SizedBox(height: 16),
          const Text(
            'Documentos incluidos',
            style: TextStyle(fontWeight: FontWeight.w700),
          ),
          const SizedBox(height: 8),
          Expanded(
            child: batch.items.isEmpty
                ? const Center(child: Text('No hay items en el lote.'))
                : ListView.separated(
                    itemCount: batch.items.length,
                    separatorBuilder: (_, __) => const Divider(height: 1),
                    itemBuilder: (context, index) {
                      final item = batch.items[index];
                      return ListTile(
                        title: Text(item.originalFilename ?? item.documentId),
                        subtitle: Text(
                          '${item.invoiceNumber ?? 'Sin numero'} · ${item.status} · ${_formatWorkflowStatus(item.workflowStatus ?? '')}',
                        ),
                      );
                    },
                  ),
          ),
        ],
      ),
    );
  }

  Widget _metaChip(String label, String value) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
      decoration: BoxDecoration(
        color: const Color(0xFFEAF4FB),
        borderRadius: BorderRadius.circular(12),
      ),
      child: Text('$label: $value'),
    );
  }

  Widget _metaLine(String label, String value) {
    return Padding(
      padding: const EdgeInsets.only(bottom: 6),
      child: Text('$label: $value'),
    );
  }
}

String _formatBatchStatus(String status) {
  switch (status) {
    case 'draft':
      return 'Borrador';
    case 'generated':
      return 'Generado';
    case 'downloaded':
      return 'Descargado';
    case 'exported':
      return 'Exportado';
    case 'error':
      return 'Error';
    default:
      return status;
  }
}

String _formatWorkflowStatus(String status) {
  switch (status) {
    case 'pending_accounting':
      return 'Pendiente contabilizar';
    case 'batched':
      return 'En lote';
    case 'exported':
      return 'Exportado';
    case 'pending_review':
      return 'Pendiente revision';
    default:
      return status.isEmpty ? '-' : status;
  }
}

String _formatDateTime(DateTime? value) {
  if (value == null) {
    return '-';
  }
  final local = value.toLocal();
  return '${local.day.toString().padLeft(2, '0')}/${local.month.toString().padLeft(2, '0')}/${local.year} ${local.hour.toString().padLeft(2, '0')}:${local.minute.toString().padLeft(2, '0')}';
}

String _formatDateShort(DateTime value) {
  final local = value.toLocal();
  return '${local.day.toString().padLeft(2, '0')}/${local.month.toString().padLeft(2, '0')}/${local.year}';
}
