import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../../core/api/api_client.dart';
import '../domain/client_invoice.dart';
import '../domain/invoice_status.dart';
import 'invoicing_providers.dart';

/// Pantalla principal de facturacion con pestanas Borradores y Emitidas.
class InvoicingScreen extends ConsumerWidget {
  const InvoicingScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final configAsync = ref.watch(invoicingConfigProvider);

    return configAsync.when(
      loading: () => Scaffold(
        appBar: AppBar(title: const Text('Facturacion')),
        body: const Center(child: CircularProgressIndicator()),
      ),
      error: (e, _) => Scaffold(
        appBar: AppBar(title: const Text('Facturacion')),
        body: Center(
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              Text('Error: ${apiErrorMessage(e)}'),
              const SizedBox(height: 8),
              OutlinedButton(
                onPressed: () => ref.invalidate(invoicingConfigProvider),
                child: const Text('Reintentar'),
              ),
            ],
          ),
        ),
      ),
      data: (config) {
        if (config['enabled'] != true) {
          return Scaffold(
            appBar: AppBar(title: const Text('Facturacion')),
            body: const Center(
              child: Text('La facturacion online no esta habilitada.'),
            ),
          );
        }
        return const _InvoicingTabs();
      },
    );
  }
}

class _InvoicingTabs extends ConsumerWidget {
  const _InvoicingTabs();

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    return DefaultTabController(
      length: 2,
      child: Scaffold(
        appBar: AppBar(
          title: const Text('Facturacion'),
          bottom: const TabBar(
            tabs: [
              Tab(text: 'Borradores'),
              Tab(text: 'Emitidas'),
            ],
          ),
          actions: [
            IconButton(
              icon: const Icon(Icons.inventory_2_outlined),
              tooltip: 'Catalogo',
              onPressed: () => context.push('/invoicing/catalog'),
            ),
            IconButton(
              icon: const Icon(Icons.people_outline),
              tooltip: 'Clientes',
              onPressed: () => context.push('/invoicing/customers'),
            ),
          ],
        ),
        body: const TabBarView(children: [_DraftsTab(), _IssuedTab()]),
        floatingActionButton: FloatingActionButton(
          onPressed: () => context.push('/invoicing/drafts/new'),
          child: const Icon(Icons.add),
        ),
      ),
    );
  }
}

class _DraftsTab extends ConsumerWidget {
  const _DraftsTab();

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final draftsAsync = ref.watch(invoiceDraftsProvider);

    return draftsAsync.when(
      loading: () => const Center(child: CircularProgressIndicator()),
      error: (e, _) => Center(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Text('Error: ${apiErrorMessage(e)}'),
            const SizedBox(height: 8),
            OutlinedButton(
              onPressed: () => ref.invalidate(invoiceDraftsProvider),
              child: const Text('Reintentar'),
            ),
          ],
        ),
      ),
      data: (drafts) {
        if (drafts.isEmpty) {
          return const Center(child: Text('No hay borradores.'));
        }
        return RefreshIndicator(
          onRefresh: () async => ref.invalidate(invoiceDraftsProvider),
          child: ListView.builder(
            itemCount: drafts.length,
            itemBuilder: (_, i) => _InvoiceTile(invoice: drafts[i]),
          ),
        );
      },
    );
  }
}

class _IssuedTab extends ConsumerWidget {
  const _IssuedTab();

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final listAsync = ref.watch(invoiceListProvider);
    final filters = ref.watch(invoiceListFiltersProvider);

    return Column(
      children: [
        _FiltersBar(filters: filters),
        Expanded(
          child: listAsync.when(
            loading: () => const Center(child: CircularProgressIndicator()),
            error: (e, _) => Center(
              child: Column(
                mainAxisSize: MainAxisSize.min,
                children: [
                  Text('Error: ${apiErrorMessage(e)}'),
                  const SizedBox(height: 8),
                  OutlinedButton(
                    onPressed: () => ref.invalidate(invoiceListProvider),
                    child: const Text('Reintentar'),
                  ),
                ],
              ),
            ),
            data: (data) {
              final items =
                  (data['items'] as List<dynamic>?)
                      ?.map(
                        (e) => ClientInvoice.fromJson(e as Map<String, dynamic>),
                      )
                      .toList() ??
                  [];
              if (items.isEmpty) {
                return const Center(child: Text('No hay facturas emitidas.'));
              }
              return RefreshIndicator(
                onRefresh: () async => ref.invalidate(invoiceListProvider),
                child: ListView.builder(
                  itemCount: items.length,
                  itemBuilder: (_, i) => _InvoiceTile(invoice: items[i]),
                ),
              );
            },
          ),
        ),
      ],
    );
  }
}

/// Filtros por ejercicio y estado (seccion 19 del encargo).
class _FiltersBar extends ConsumerWidget {
  const _FiltersBar({required this.filters});

  final InvoiceListFilters filters;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final currentYear = DateTime.now().year;
    final years = [currentYear, currentYear - 1, currentYear - 2];

    return Padding(
      padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
      child: SingleChildScrollView(
        scrollDirection: Axis.horizontal,
        child: Row(
          children: [
            FilterChip(
              label: Text(filters.fiscalYear?.toString() ?? 'Ejercicio'),
              selected: filters.fiscalYear != null,
              onSelected: (_) async {
                final selected = await showDialog<int?>(
                  context: context,
                  builder: (ctx) => SimpleDialog(
                    title: const Text('Ejercicio'),
                    children: [
                      SimpleDialogOption(
                        onPressed: () => Navigator.pop(ctx, null),
                        child: const Text('Todos'),
                      ),
                      for (final year in years)
                        SimpleDialogOption(
                          onPressed: () => Navigator.pop(ctx, year),
                          child: Text('$year'),
                        ),
                    ],
                  ),
                );
                ref.read(invoiceListFiltersProvider.notifier).state = filters
                    .copyWith(
                      fiscalYear: selected,
                      clearFiscalYear: selected == null,
                    );
              },
            ),
            const SizedBox(width: 8),
            FilterChip(
              label: Text(_statusLabel(filters.status)),
              selected: filters.status != null,
              onSelected: (_) async {
                final selected = await showDialog<String?>(
                  context: context,
                  builder: (ctx) => SimpleDialog(
                    title: const Text('Estado'),
                    children: [
                      SimpleDialogOption(
                        onPressed: () => Navigator.pop(ctx, null),
                        child: const Text('Todos'),
                      ),
                      for (final status in const [
                        'issued_pending_processing',
                        'rendered',
                        'emailed',
                        'processing_error',
                        'cancelled',
                        'replaced',
                      ])
                        SimpleDialogOption(
                          onPressed: () => Navigator.pop(ctx, status),
                          child: Text(InvoiceStatus.fromString(status).label),
                        ),
                    ],
                  ),
                );
                ref.read(invoiceListFiltersProvider.notifier).state = filters
                    .copyWith(status: selected, clearStatus: selected == null);
              },
            ),
            if (filters.fiscalYear != null || filters.status != null) ...[
              const SizedBox(width: 8),
              ActionChip(
                avatar: const Icon(Icons.close, size: 16),
                label: const Text('Limpiar'),
                onPressed: () {
                  ref.read(invoiceListFiltersProvider.notifier).state =
                      const InvoiceListFilters();
                },
              ),
            ],
          ],
        ),
      ),
    );
  }

  String _statusLabel(String? status) {
    if (status == null) return 'Estado';
    return InvoiceStatus.fromString(status).label;
  }
}

class _InvoiceTile extends StatelessWidget {
  const _InvoiceTile({required this.invoice});

  final ClientInvoice invoice;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final isDraft = invoice.invoiceStatus == InvoiceLifecycleStatus.draft;
    final hasFiscalProblem = invoice.fiscalStatus.isProblem;
    return ListTile(
      leading: Icon(
        isDraft
            ? Icons.edit_note
            : invoice.invoiceStatus == InvoiceLifecycleStatus.cancelled
            ? Icons.block
            : hasFiscalProblem
            ? Icons.error_outline
            : invoice.pdfStatus != PdfStatus.generated
            ? Icons.hourglass_empty
            : Icons.receipt_long,
        color: hasFiscalProblem ? theme.colorScheme.error : null,
      ),
      title: Text(invoice.displayNumber),
      subtitle: Text(
        [
          invoice.invoiceStatus.label,
          if (!isDraft) invoice.deliveryStatus.label,
          if (invoice.invoiceDate != null)
            invoice.invoiceDate!.substring(0, 10),
          '${invoice.total} ${invoice.currency}',
        ].join(' · '),
      ),
      trailing: invoice.isReadOnlyFromDesktop
          ? const Icon(Icons.desktop_windows_outlined, size: 18)
          : const Icon(Icons.chevron_right),
      onTap: () {
        if (isDraft) {
          context.push('/invoicing/drafts/${invoice.id}');
        } else {
          context.push('/invoicing/invoices/${invoice.id}');
        }
      },
    );
  }
}
