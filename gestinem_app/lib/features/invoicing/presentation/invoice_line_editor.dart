import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../domain/client_invoice.dart';
import 'invoicing_providers.dart';

/// Datos mutables de una linea de factura en edicion. Compartido entre el
/// formulario de borrador y el de rectificativa.
class InvoiceLineData {
  InvoiceLineData({
    this.description = '',
    this.quantity = '1',
    this.unitPrice = '0',
    this.discountPercent = '0',
    this.vatRate = '21.00',
    this.catalogItemId,
  });

  String description;
  String quantity;
  String unitPrice;
  String discountPercent;
  String vatRate;
  String? catalogItemId;

  Map<String, dynamic> toJson() => {
    'description': description,
    'quantity': quantity,
    'unit_price': unitPrice,
    'discount_percent': discountPercent,
    'vat_rate': vatRate,
    if (catalogItemId != null) 'catalog_item_id': catalogItemId,
  };
}

/// Editor de una linea de factura, con selector opcional de catalogo.
class InvoiceLineEditor extends ConsumerWidget {
  const InvoiceLineEditor({
    super.key,
    required this.data,
    required this.index,
    required this.canRemove,
    required this.onRemove,
    required this.onChanged,
  });

  final InvoiceLineData data;
  final int index;
  final bool canRemove;
  final VoidCallback onRemove;
  final VoidCallback onChanged;

  Future<void> _pickFromCatalog(BuildContext context, WidgetRef ref) async {
    final picked = await showModalBottomSheet<CatalogItem>(
      context: context,
      isScrollControlled: true,
      builder: (ctx) => const _CatalogPickerSheet(),
    );
    if (picked != null) {
      data.catalogItemId = picked.id;
      data.description = picked.description;
      data.unitPrice = picked.unitPrice;
      data.vatRate = picked.vatRate;
      onChanged();
    }
  }

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    return Card(
      margin: const EdgeInsets.only(bottom: 8),
      child: Padding(
        padding: const EdgeInsets.all(12),
        child: Column(
          children: [
            Row(
              children: [
                Text(
                  'Linea ${index + 1}',
                  style: const TextStyle(fontWeight: FontWeight.w600),
                ),
                if (data.catalogItemId != null) ...[
                  const SizedBox(width: 8),
                  const Icon(Icons.inventory_2_outlined, size: 16),
                ],
                const Spacer(),
                TextButton.icon(
                  onPressed: () => _pickFromCatalog(context, ref),
                  icon: const Icon(Icons.search, size: 18),
                  label: const Text('Catalogo'),
                ),
                if (canRemove)
                  IconButton(
                    icon: const Icon(Icons.remove_circle_outline, size: 20),
                    onPressed: onRemove,
                  ),
              ],
            ),
            TextFormField(
              key: ValueKey('desc-${data.hashCode}-$index'),
              initialValue: data.description,
              decoration: const InputDecoration(labelText: 'Concepto *'),
              onChanged: (v) => data.description = v,
              validator: (v) => v == null || v.trim().isEmpty
                  ? 'El concepto es obligatorio'
                  : null,
            ),
            const SizedBox(height: 8),
            Row(
              children: [
                Expanded(
                  child: TextFormField(
                    initialValue: data.quantity,
                    decoration: const InputDecoration(labelText: 'Cantidad'),
                    keyboardType: const TextInputType.numberWithOptions(
                      decimal: true,
                    ),
                    onChanged: (v) => data.quantity = v,
                  ),
                ),
                const SizedBox(width: 8),
                Expanded(
                  child: TextFormField(
                    initialValue: data.unitPrice,
                    decoration: const InputDecoration(
                      labelText: 'Precio unidad',
                    ),
                    keyboardType: const TextInputType.numberWithOptions(
                      decimal: true,
                    ),
                    onChanged: (v) {
                      data.unitPrice = v;
                      data.catalogItemId = null;
                    },
                  ),
                ),
              ],
            ),
            const SizedBox(height: 8),
            Row(
              children: [
                Expanded(
                  child: TextFormField(
                    initialValue: data.discountPercent,
                    decoration: const InputDecoration(labelText: 'Dto %'),
                    keyboardType: const TextInputType.numberWithOptions(
                      decimal: true,
                    ),
                    onChanged: (v) => data.discountPercent = v,
                  ),
                ),
                const SizedBox(width: 8),
                Expanded(
                  child: DropdownButtonFormField<String>(
                    initialValue: data.vatRate,
                    decoration: const InputDecoration(labelText: 'IVA %'),
                    items: const [
                      DropdownMenuItem(value: '0', child: Text('0%')),
                      DropdownMenuItem(value: '4.00', child: Text('4%')),
                      DropdownMenuItem(value: '10.00', child: Text('10%')),
                      DropdownMenuItem(value: '21.00', child: Text('21%')),
                    ],
                    onChanged: (v) {
                      if (v != null) data.vatRate = v;
                    },
                  ),
                ),
              ],
            ),
          ],
        ),
      ),
    );
  }
}

class _CatalogPickerSheet extends ConsumerWidget {
  const _CatalogPickerSheet();

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final itemsAsync = ref.watch(catalogItemsProvider);
    return SafeArea(
      child: FractionallySizedBox(
        heightFactor: 0.75,
        child: Column(
          children: [
            Padding(
              padding: const EdgeInsets.all(16),
              child: Row(
                children: [
                  Text(
                    'Elegir del catalogo',
                    style: Theme.of(context).textTheme.titleMedium,
                  ),
                  const Spacer(),
                  TextButton.icon(
                    onPressed: () => context.push('/invoicing/catalog/new'),
                    icon: const Icon(Icons.add, size: 18),
                    label: const Text('Nuevo'),
                  ),
                ],
              ),
            ),
            Expanded(
              child: itemsAsync.when(
                loading: () =>
                    const Center(child: CircularProgressIndicator()),
                error: (e, _) => Center(child: Text('Error: $e')),
                data: (items) {
                  if (items.isEmpty) {
                    return const Center(
                      child: Text('No hay articulos en el catalogo.'),
                    );
                  }
                  return ListView.builder(
                    itemCount: items.length,
                    itemBuilder: (_, i) {
                      final item = items[i];
                      return ListTile(
                        title: Text(item.description),
                        subtitle: Text('${item.unitPrice} EUR · IVA ${item.vatRate}%'),
                        onTap: () => Navigator.of(context).pop(item),
                      );
                    },
                  );
                },
              ),
            ),
          ],
        ),
      ),
    );
  }
}
