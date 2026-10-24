import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../../core/api/api_client.dart';
import '../domain/client_invoice.dart';
import 'invoicing_providers.dart';

/// Catalogo de productos y servicios de la organizacion.
class CatalogListScreen extends ConsumerWidget {
  const CatalogListScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final itemsAsync = ref.watch(catalogItemsProvider);

    return Scaffold(
      appBar: AppBar(
        title: const Text('Catalogo'),
        bottom: PreferredSize(
          preferredSize: const Size.fromHeight(56),
          child: Padding(
            padding: const EdgeInsets.fromLTRB(16, 0, 16, 12),
            child: TextField(
              decoration: const InputDecoration(
                hintText: 'Buscar por descripcion o codigo',
                prefixIcon: Icon(Icons.search),
                isDense: true,
                filled: true,
              ),
              onChanged: (v) =>
                  ref.read(catalogSearchProvider.notifier).state = v,
            ),
          ),
        ),
      ),
      body: itemsAsync.when(
        loading: () => const Center(child: CircularProgressIndicator()),
        error: (e, _) => Center(
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              Text('Error: ${apiErrorMessage(e)}'),
              const SizedBox(height: 8),
              OutlinedButton(
                onPressed: () => ref.invalidate(catalogItemsProvider),
                child: const Text('Reintentar'),
              ),
            ],
          ),
        ),
        data: (items) {
          if (items.isEmpty) {
            return const Center(
              child: Text('No hay productos ni servicios todavia.'),
            );
          }
          return ListView.builder(
            itemCount: items.length,
            itemBuilder: (_, i) => _CatalogTile(item: items[i]),
          );
        },
      ),
      floatingActionButton: FloatingActionButton(
        onPressed: () async {
          final changed = await context.push<bool>('/invoicing/catalog/new');
          if (changed == true) ref.invalidate(catalogItemsProvider);
        },
        child: const Icon(Icons.add),
      ),
    );
  }
}

class _CatalogTile extends ConsumerWidget {
  const _CatalogTile({required this.item});

  final CatalogItem item;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    return ListTile(
      leading: Icon(item.isProduct ? Icons.inventory_2_outlined : Icons.handyman_outlined),
      title: Text(item.description),
      subtitle: Text(
        [
          if (item.code.isNotEmpty) item.code,
          '${item.unitPrice} EUR${item.unit.isNotEmpty ? ' / ${item.unit}' : ''}',
          'IVA ${item.vatRate}%',
        ].join(' · '),
      ),
      trailing: const Icon(Icons.chevron_right),
      onTap: () async {
        final changed = await context.push<bool>(
          '/invoicing/catalog/${item.id}',
        );
        if (changed == true) ref.invalidate(catalogItemsProvider);
      },
    );
  }
}
