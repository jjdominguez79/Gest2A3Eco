import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../../core/api/api_client.dart';
import '../domain/client_invoice.dart';
import '../domain/invoice_status.dart';
import 'invoicing_providers.dart';

/// Pantalla de detalle de una factura emitida (solo lectura: una factura
/// emitida nunca se edita ni se elimina, seccion 15 del encargo).
class InvoiceDetailScreen extends ConsumerWidget {
  const InvoiceDetailScreen({super.key, required this.invoiceId});

  final String invoiceId;

  Future<void> _cancel(BuildContext context, WidgetRef ref) async {
    final reasonController = TextEditingController();
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('Anular factura'),
        content: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            const Text(
              'Se registrara una anulacion fiscal. La factura original no '
              'se modifica ni se elimina.',
            ),
            const SizedBox(height: 12),
            TextField(
              controller: reasonController,
              decoration: const InputDecoration(labelText: 'Motivo *'),
              maxLines: 2,
            ),
          ],
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(ctx, false),
            child: const Text('Cancelar'),
          ),
          FilledButton(
            onPressed: () => Navigator.pop(ctx, true),
            style: FilledButton.styleFrom(
              backgroundColor: Theme.of(ctx).colorScheme.error,
            ),
            child: const Text('Anular'),
          ),
        ],
      ),
    );
    if (confirmed != true) return;
    if (reasonController.text.trim().isEmpty) {
      if (context.mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(content: Text('Indica el motivo de la anulacion')),
        );
      }
      return;
    }
    try {
      await ref
          .read(invoicingRepositoryProvider)
          .cancelInvoice(invoiceId, reason: reasonController.text.trim());
      ref.invalidate(invoiceDetailProvider(invoiceId));
      ref.invalidate(invoiceListProvider);
      if (context.mounted) {
        ScaffoldMessenger.of(
          context,
        ).showSnackBar(const SnackBar(content: Text('Factura anulada')));
      }
    } catch (e) {
      if (context.mounted) {
        ScaffoldMessenger.of(
          context,
        ).showSnackBar(SnackBar(content: Text(apiErrorMessage(e))));
      }
    }
  }

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final detailAsync = ref.watch(invoiceDetailProvider(invoiceId));

    return Scaffold(
      appBar: AppBar(
        title: const Text('Detalle factura'),
        actions: [
          detailAsync.maybeWhen(
            data: (invoice) => invoice.invoiceStatus !=
                    InvoiceLifecycleStatus.draft
                ? IconButton(
                    icon: const Icon(Icons.picture_as_pdf_outlined),
                    tooltip: 'Ver PDF',
                    onPressed: () =>
                        context.push('/invoicing/invoices/$invoiceId/pdf'),
                  )
                : const SizedBox.shrink(),
            orElse: () => const SizedBox.shrink(),
          ),
          detailAsync.maybeWhen(
            data: (invoice) => (invoice.canRectify || invoice.canCancel)
                ? PopupMenuButton<String>(
                    onSelected: (value) {
                      if (value == 'rectify') {
                        context.push('/invoicing/invoices/$invoiceId/rectify');
                      } else if (value == 'cancel') {
                        _cancel(context, ref);
                      }
                    },
                    itemBuilder: (ctx) => [
                      if (invoice.canRectify)
                        const PopupMenuItem(
                          value: 'rectify',
                          child: Text('Crear rectificativa'),
                        ),
                      if (invoice.canCancel)
                        const PopupMenuItem(
                          value: 'cancel',
                          child: Text('Anular factura'),
                        ),
                    ],
                  )
                : const SizedBox.shrink(),
            orElse: () => const SizedBox.shrink(),
          ),
        ],
      ),
      body: detailAsync.when(
        loading: () => const Center(child: CircularProgressIndicator()),
        error: (e, _) => Center(
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              Text('Error: ${apiErrorMessage(e)}'),
              const SizedBox(height: 8),
              OutlinedButton(
                onPressed: () => ref.invalidate(invoiceDetailProvider(invoiceId)),
                child: const Text('Reintentar'),
              ),
            ],
          ),
        ),
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
        if (invoice.isReadOnlyFromDesktop)
          Padding(
            padding: const EdgeInsets.only(bottom: 12),
            child: Chip(
              avatar: const Icon(Icons.desktop_windows_outlined, size: 18),
              label: const Text('Factura del escritorio (solo lectura)'),
            ),
          ),

        // Estados separados: emision, fiscal, PDF, entrega, contabilidad.
        // Nunca se mezclan: un problema contable no es un problema fiscal.
        _StatusGrid(invoice: invoice),
        const SizedBox(height: 16),

        if (invoice.invoiceStatus == InvoiceLifecycleStatus.cancelled)
          _NoticeCard(
            color: Colors.red.shade50,
            icon: Icons.block,
            iconColor: Colors.red.shade700,
            title: 'Factura anulada',
            message: invoice.cancellationReason.isNotEmpty
                ? invoice.cancellationReason
                : 'Esta factura ha sido anulada.',
          ),
        if (invoice.invoiceStatus == InvoiceLifecycleStatus.rectified)
          _NoticeCard(
            color: Colors.blue.shade50,
            icon: Icons.sync_alt,
            iconColor: Colors.blue.shade700,
            title: 'Factura rectificada',
            message: 'Existe una factura rectificativa que la corrige.',
          ),
        if (invoice.rectifiesInvoiceId != null)
          _NoticeCard(
            color: Colors.blue.shade50,
            icon: Icons.sync_alt,
            iconColor: Colors.blue.shade700,
            title: 'Factura rectificativa',
            message: 'Corrige una factura emitida anteriormente.',
          ),
        if (invoice.fiscalStatus.isProblem)
          _NoticeCard(
            color: Colors.orange.shade50,
            icon: Icons.warning_amber_rounded,
            iconColor: Colors.orange.shade800,
            title: 'Incidencia fiscal',
            message:
                'El registro fiscal de esta factura tiene una incidencia '
                '(${invoice.fiscalStatus.label.toLowerCase()}). '
                'El documento sigue siendo valido; Gestinem revisara el envio.',
          ),
        if (invoice.accountingSyncStatus == AccountingSyncStatus.reviewRequired ||
            invoice.accountingSyncStatus == AccountingSyncStatus.error)
          _NoticeCard(
            color: Colors.grey.shade100,
            icon: Icons.account_balance_outlined,
            iconColor: Colors.grey.shade700,
            title: 'Pendiente de revision contable',
            message:
                'La incorporacion a la contabilidad de Gestinem requiere '
                'revision. Esto no afecta a la validez fiscal de tu factura.',
          ),

        const SizedBox(height: 4),

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
                _InfoRow('Origen', invoice.sourceSystem.label),
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

/// Cuadricula con los 5 estados separados de la factura (seccion 8/19).
class _StatusGrid extends StatelessWidget {
  const _StatusGrid({required this.invoice});

  final ClientInvoice invoice;

  @override
  Widget build(BuildContext context) {
    return Wrap(
      spacing: 8,
      runSpacing: 8,
      children: [
        _StatusChip(
          label: 'Emision',
          value: invoice.invoiceStatus.label,
          color: switch (invoice.invoiceStatus) {
            InvoiceLifecycleStatus.issued => Colors.green,
            InvoiceLifecycleStatus.cancelled => Colors.red,
            InvoiceLifecycleStatus.rectified => Colors.blue,
            InvoiceLifecycleStatus.draft => Colors.grey,
          },
        ),
        _StatusChip(
          label: 'Fiscal',
          value: invoice.fiscalStatus.label,
          color: invoice.fiscalStatus.isProblem
              ? Colors.orange
              : invoice.fiscalStatus == FiscalStatus.accepted
              ? Colors.green
              : Colors.grey,
        ),
        _StatusChip(
          label: 'PDF',
          value: invoice.pdfStatus.label,
          color: invoice.pdfStatus == PdfStatus.generated
              ? Colors.green
              : invoice.pdfStatus == PdfStatus.error
              ? Colors.red
              : Colors.grey,
        ),
        _StatusChip(
          label: 'Entrega',
          value: invoice.deliveryStatus.label,
          color: invoice.deliveryStatus == DeliveryStatus.sent
              ? Colors.green
              : invoice.deliveryStatus == DeliveryStatus.error
              ? Colors.red
              : Colors.grey,
        ),
        _StatusChip(
          label: 'Contabilidad',
          value: invoice.accountingSyncStatus.label,
          color: invoice.accountingSyncStatus == AccountingSyncStatus.imported
              ? Colors.green
              : invoice.accountingSyncStatus == AccountingSyncStatus.error ||
                    invoice.accountingSyncStatus ==
                        AccountingSyncStatus.reviewRequired
              ? Colors.orange
              : Colors.grey,
        ),
      ],
    );
  }
}

class _StatusChip extends StatelessWidget {
  const _StatusChip({
    required this.label,
    required this.value,
    required this.color,
  });

  final String label;
  final String value;
  final MaterialColor color;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 6),
      decoration: BoxDecoration(
        color: color.shade50,
        borderRadius: BorderRadius.circular(8),
        border: Border.all(color: color.shade200),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        mainAxisSize: MainAxisSize.min,
        children: [
          Text(
            label.toUpperCase(),
            style: TextStyle(
              fontSize: 10,
              color: color.shade700,
              fontWeight: FontWeight.w600,
            ),
          ),
          Text(
            value,
            style: TextStyle(color: color.shade900, fontSize: 13),
          ),
        ],
      ),
    );
  }
}

class _NoticeCard extends StatelessWidget {
  const _NoticeCard({
    required this.color,
    required this.icon,
    required this.iconColor,
    required this.title,
    required this.message,
  });

  final Color color;
  final IconData icon;
  final Color iconColor;
  final String title;
  final String message;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.only(bottom: 12),
      child: Card(
        color: color,
        child: Padding(
          padding: const EdgeInsets.all(12),
          child: Row(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Icon(icon, color: iconColor, size: 22),
              const SizedBox(width: 10),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      title,
                      style: const TextStyle(fontWeight: FontWeight.bold),
                    ),
                    const SizedBox(height: 2),
                    Text(message),
                  ],
                ),
              ),
            ],
          ),
        ),
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
