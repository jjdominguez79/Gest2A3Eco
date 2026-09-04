import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../../core/api/api_client.dart';
import '../domain/client_invoice.dart';
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
        body: Center(child: Text('Error: ${apiErrorMessage(e)}')),
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
      error: (e, _) => Center(child: Text('Error: ${apiErrorMessage(e)}')),
      data: (drafts) {
        if (drafts.isEmpty) {
          return const Center(child: Text('No hay borradores.'));
        }
        return ListView.builder(
          itemCount: drafts.length,
          itemBuilder: (_, i) => _InvoiceTile(invoice: drafts[i]),
        );
      },
    );
  }
}

class _IssuedTab extends ConsumerWidget {
  const _IssuedTab();

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final repo = ref.watch(invoicingRepositoryProvider);

    return FutureBuilder<Map<String, dynamic>>(
      future: repo.listInvoices(),
      builder: (context, snapshot) {
        if (snapshot.connectionState == ConnectionState.waiting) {
          return const Center(child: CircularProgressIndicator());
        }
        if (snapshot.hasError) {
          return Center(child: Text('Error: ${snapshot.error}'));
        }
        final data = snapshot.data!;
        final items =
            (data['items'] as List<dynamic>?)
                ?.map((e) => ClientInvoice.fromJson(e as Map<String, dynamic>))
                .toList() ??
            [];
        if (items.isEmpty) {
          return const Center(child: Text('No hay facturas emitidas.'));
        }
        return ListView.builder(
          itemCount: items.length,
          itemBuilder: (_, i) => _InvoiceTile(invoice: items[i]),
        );
      },
    );
  }
}

class _InvoiceTile extends StatelessWidget {
  const _InvoiceTile({required this.invoice});

  final ClientInvoice invoice;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return ListTile(
      leading: Icon(
        invoice.status.isDraft
            ? Icons.edit_note
            : invoice.status.isError
            ? Icons.error_outline
            : invoice.status.isProcessing
            ? Icons.hourglass_empty
            : Icons.receipt_long,
        color: invoice.status.isError ? theme.colorScheme.error : null,
      ),
      title: Text(invoice.displayNumber),
      subtitle: Text(
        [
          invoice.status.label,
          if (invoice.invoiceDate != null)
            invoice.invoiceDate!.substring(0, 10),
          '${invoice.total} ${invoice.currency}',
        ].join(' · '),
      ),
      trailing: const Icon(Icons.chevron_right),
      onTap: () {
        if (invoice.status.isDraft) {
          context.push('/invoicing/drafts/${invoice.id}');
        } else {
          context.push('/invoicing/invoices/${invoice.id}');
        }
      },
    );
  }
}
