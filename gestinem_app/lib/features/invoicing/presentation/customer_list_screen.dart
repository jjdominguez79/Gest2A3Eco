import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../../core/api/api_client.dart';
import '../domain/client_invoice.dart';
import 'invoicing_providers.dart';

/// Directorio de clientes para facturacion.
class CustomerListScreen extends ConsumerWidget {
  const CustomerListScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final customersAsync = ref.watch(invoiceCustomersProvider);

    return Scaffold(
      appBar: AppBar(title: const Text('Clientes')),
      body: customersAsync.when(
        loading: () => const Center(child: CircularProgressIndicator()),
        error: (e, _) => Center(child: Text('Error: ${apiErrorMessage(e)}')),
        data: (customers) {
          if (customers.isEmpty) {
            return const Center(child: Text('No hay clientes registrados.'));
          }
          return ListView.builder(
            itemCount: customers.length,
            itemBuilder: (_, i) => _CustomerTile(customer: customers[i]),
          );
        },
      ),
      floatingActionButton: FloatingActionButton(
        onPressed: () async {
          final created = await context.push<bool>('/invoicing/customers/new');
          if (created == true) {
            ref.invalidate(invoiceCustomersProvider);
          }
        },
        child: const Icon(Icons.person_add),
      ),
    );
  }
}

class _CustomerTile extends StatelessWidget {
  const _CustomerTile({required this.customer});

  final InvoiceCustomer customer;

  @override
  Widget build(BuildContext context) {
    return ListTile(
      leading: CircleAvatar(
        child: Text(
          customer.legalName.isNotEmpty
              ? customer.legalName[0].toUpperCase()
              : '?',
        ),
      ),
      title: Text(customer.legalName),
      subtitle: Text(customer.taxId),
      trailing: customer.pendingDesktopImport
          ? const Chip(label: Text('Pendiente'))
          : customer.active
          ? null
          : const Chip(label: Text('Inactivo')),
    );
  }
}
