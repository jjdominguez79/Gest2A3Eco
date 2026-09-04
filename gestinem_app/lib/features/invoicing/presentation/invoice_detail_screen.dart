import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../core/api/api_client.dart';
import '../domain/client_invoice.dart';
import '../domain/invoice_status.dart';
import 'invoicing_providers.dart';

/// Pantalla de detalle de una factura emitida (solo lectura).
class InvoiceDetailScreen extends ConsumerWidget {
  const InvoiceDetailScreen({super.key, required this.invoiceId});

  final String invoiceId;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final detailAsync = ref.watch(invoiceDetailProvider(invoiceId));

    return Scaffold(
      appBar: AppBar(title: const Text('Detalle factura')),
      body: detailAsync.when(
        loading: () => const Center(child: CircularProgressIndicator()),
        error: (e, _) => Center(child: Text('Error: ${apiErrorMessage(e)}')),
        data: (invoice) => _InvoiceDetailBody(invoice: invoice),
      ),
    );
  }
}

class _InvoiceDetailBody extends StatelessWidget {
  const _InvoiceDetailBody({required this.invoice});

  final ClientInvoice invoice;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return ListView(
      padding: const EdgeInsets.all(16),
      children: [
        // Status banner
        _StatusBanner(status: invoice.status),
        const SizedBox(height: 16),

        // Header info
        Card(
          child: Padding(
            padding: const EdgeInsets.all(16),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  invoice.displayNumber,
                  style: theme.textTheme.headlineSmall,
                ),
                const SizedBox(height: 8),
                if (invoice.invoiceDate != null)
                  _InfoRow('Fecha', invoice.invoiceDate!.substring(0, 10)),
                _InfoRow('Serie', invoice.seriesCode),
                _InfoRow('Ejercicio', '${invoice.fiscalYear}'),
                if (invoice.paymentMethod.isNotEmpty)
                  _InfoRow('Forma de pago', invoice.paymentMethod),
                if (invoice.notes.isNotEmpty) _InfoRow('Notas', invoice.notes),
              ],
            ),
          ),
        ),
        const SizedBox(height: 12),

        // Lines
        if (invoice.lines.isNotEmpty) ...[
          Text('Lineas', style: theme.textTheme.titleMedium),
          const SizedBox(height: 8),
          ...invoice.lines.map(
            (line) => Card(
              child: ListTile(
                title: Text(
                  line.description.isNotEmpty
                      ? line.description
                      : 'Linea ${line.lineNumber}',
                ),
                subtitle: Text(
                  '${line.quantity} x ${line.unitPrice} EUR '
                  '(IVA ${line.vatRate}%)',
                ),
                trailing: Text(
                  '${line.lineTotal} EUR',
                  style: theme.textTheme.bodyMedium?.copyWith(
                    fontWeight: FontWeight.bold,
                  ),
                ),
              ),
            ),
          ),
          const SizedBox(height: 12),
        ],

        // Totals
        Card(
          child: Padding(
            padding: const EdgeInsets.all(16),
            child: Column(
              children: [
                _TotalRow('Base imponible', '${invoice.subtotal} EUR'),
                _TotalRow('IVA', '${invoice.totalVat} EUR'),
                if (invoice.withholdingAmount != '0')
                  _TotalRow(
                    'Retencion (${invoice.withholdingRate}%)',
                    '-${invoice.withholdingAmount} EUR',
                  ),
                const Divider(),
                _TotalRow(
                  'Total',
                  '${invoice.total} ${invoice.currency}',
                  bold: true,
                ),
              ],
            ),
          ),
        ),
      ],
    );
  }
}

class _StatusBanner extends StatelessWidget {
  const _StatusBanner({required this.status});

  final InvoiceStatus status;

  @override
  Widget build(BuildContext context) {
    final Color color;
    final IconData icon;
    if (status.isError) {
      color = Theme.of(context).colorScheme.error;
      icon = Icons.error_outline;
    } else if (status.isProcessing) {
      color = Colors.orange;
      icon = Icons.hourglass_empty;
    } else if (status.isComplete) {
      color = Colors.green;
      icon = Icons.check_circle_outline;
    } else {
      color = Colors.grey;
      icon = Icons.info_outline;
    }

    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
      decoration: BoxDecoration(
        color: color.withValues(alpha: 0.1),
        borderRadius: BorderRadius.circular(8),
        border: Border.all(color: color.withValues(alpha: 0.3)),
      ),
      child: Row(
        children: [
          Icon(icon, color: color, size: 20),
          const SizedBox(width: 8),
          Text(
            status.label,
            style: TextStyle(color: color, fontWeight: FontWeight.w600),
          ),
        ],
      ),
    );
  }
}

class _InfoRow extends StatelessWidget {
  const _InfoRow(this.label, this.value);

  final String label;
  final String value;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 2),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          SizedBox(
            width: 120,
            child: Text(
              label,
              style: const TextStyle(fontWeight: FontWeight.w500),
            ),
          ),
          Expanded(child: Text(value)),
        ],
      ),
    );
  }
}

class _TotalRow extends StatelessWidget {
  const _TotalRow(this.label, this.value, {this.bold = false});

  final String label;
  final String value;
  final bool bold;

  @override
  Widget build(BuildContext context) {
    final style = bold
        ? const TextStyle(fontWeight: FontWeight.bold, fontSize: 16)
        : null;
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 4),
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
