import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../../core/api/api_client.dart';
import 'invoicing_providers.dart';

/// Pantalla de confirmacion irreversible antes de emitir un borrador.
class IssueConfirmationScreen extends ConsumerStatefulWidget {
  const IssueConfirmationScreen({super.key, required this.draftId});

  final String draftId;

  @override
  ConsumerState<IssueConfirmationScreen> createState() =>
      _IssueConfirmationScreenState();
}

class _IssueConfirmationScreenState
    extends ConsumerState<IssueConfirmationScreen> {
  bool _issuing = false;

  Future<void> _issue() async {
    setState(() => _issuing = true);
    try {
      final repo = ref.read(invoicingRepositoryProvider);
      final invoice = await repo.issueDraft(widget.draftId);
      ref.invalidate(invoiceDraftsProvider);
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(
            content: Text('Factura ${invoice.displayNumber} emitida'),
          ),
        );
        context.go('/invoicing/invoices/${invoice.id}');
      }
    } catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text(apiErrorMessage(e))),
        );
        setState(() => _issuing = false);
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    final draftAsync = ref.watch(draftDetailProvider(widget.draftId));
    final theme = Theme.of(context);

    return Scaffold(
      appBar: AppBar(title: const Text('Emitir factura')),
      body: draftAsync.when(
        loading: () => const Center(child: CircularProgressIndicator()),
        error: (e, _) => Center(child: Text('Error: ${apiErrorMessage(e)}')),
        data: (draft) => Padding(
          padding: const EdgeInsets.all(16),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              // Warning card
              Card(
                color: Colors.amber.shade50,
                child: Padding(
                  padding: const EdgeInsets.all(16),
                  child: Row(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Icon(Icons.warning_amber_rounded,
                          color: Colors.amber.shade800, size: 28),
                      const SizedBox(width: 12),
                      Expanded(
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            Text(
                              'Accion irreversible',
                              style: theme.textTheme.titleMedium?.copyWith(
                                fontWeight: FontWeight.bold,
                              ),
                            ),
                            const SizedBox(height: 4),
                            const Text(
                              'Una vez emitida, la factura recibira un numero '
                              'definitivo y no podra modificarse ni eliminarse. '
                              'Se enviara a procesamiento automatico.',
                            ),
                          ],
                        ),
                      ),
                    ],
                  ),
                ),
              ),
              const SizedBox(height: 16),

              // Draft summary
              Card(
                child: Padding(
                  padding: const EdgeInsets.all(16),
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text('Resumen del borrador',
                          style: theme.textTheme.titleMedium),
                      const SizedBox(height: 12),
                      _SummaryRow('Lineas', '${draft.lines.length}'),
                      _SummaryRow('Base imponible', '${draft.subtotal} EUR'),
                      _SummaryRow('IVA', '${draft.totalVat} EUR'),
                      if (draft.withholdingAmount != '0')
                        _SummaryRow(
                          'Retencion',
                          '-${draft.withholdingAmount} EUR',
                        ),
                      const Divider(),
                      _SummaryRow(
                        'Total',
                        '${draft.total} ${draft.currency}',
                        bold: true,
                      ),
                      if (draft.recipientEmail.isNotEmpty) ...[
                        const SizedBox(height: 8),
                        _SummaryRow('Email', draft.recipientEmail),
                      ],
                    ],
                  ),
                ),
              ),

              const Spacer(),

              // Action buttons
              Row(
                children: [
                  Expanded(
                    child: OutlinedButton(
                      onPressed: _issuing ? null : () => context.pop(),
                      child: const Text('Cancelar'),
                    ),
                  ),
                  const SizedBox(width: 12),
                  Expanded(
                    flex: 2,
                    child: FilledButton.icon(
                      onPressed: _issuing ? null : _issue,
                      icon: _issuing
                          ? const SizedBox(
                              height: 18,
                              width: 18,
                              child:
                                  CircularProgressIndicator(strokeWidth: 2),
                            )
                          : const Icon(Icons.send),
                      label: const Text('Confirmar emision'),
                    ),
                  ),
                ],
              ),
              const SizedBox(height: 16),
            ],
          ),
        ),
      ),
    );
  }
}

class _SummaryRow extends StatelessWidget {
  const _SummaryRow(this.label, this.value, {this.bold = false});

  final String label;
  final String value;
  final bool bold;

  @override
  Widget build(BuildContext context) {
    final style = bold
        ? const TextStyle(fontWeight: FontWeight.bold, fontSize: 16)
        : null;
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 2),
      child: Row(
        mainAxisAlignment: MainAxisAlignment.spaceBetween,
        children: [
          Text(label, style: style),
          Text(value, style: style),
        ],
      ),
    );
  }
}
