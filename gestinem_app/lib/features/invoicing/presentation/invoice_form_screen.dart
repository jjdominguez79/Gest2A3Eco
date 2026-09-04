import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../../core/api/api_client.dart';
import 'invoicing_providers.dart';

/// Formulario para crear o editar un borrador de factura.
class InvoiceFormScreen extends ConsumerStatefulWidget {
  const InvoiceFormScreen({super.key, this.draftId});

  final String? draftId;

  @override
  ConsumerState<InvoiceFormScreen> createState() => _InvoiceFormScreenState();
}

class _InvoiceFormScreenState extends ConsumerState<InvoiceFormScreen> {
  final _formKey = GlobalKey<FormState>();
  bool _loading = true;
  bool _saving = false;

  String? _customerId;
  final _invoiceDate = TextEditingController();
  final _paymentMethod = TextEditingController();
  final _notes = TextEditingController();
  final _recipientEmail = TextEditingController();
  String _withholdingRate = '0';

  List<_LineData> _lines = [_LineData()];

  bool get _isEdit => widget.draftId != null;

  @override
  void initState() {
    super.initState();
    if (_isEdit) {
      _loadDraft();
    } else {
      _loading = false;
    }
  }

  Future<void> _loadDraft() async {
    try {
      final repo = ref.read(invoicingRepositoryProvider);
      final draft = await repo.getDraft(widget.draftId!);
      if (!mounted) return;
      setState(() {
        _customerId = draft.customerId.isNotEmpty ? draft.customerId : null;
        _invoiceDate.text = draft.invoiceDate ?? '';
        _paymentMethod.text = draft.paymentMethod;
        _notes.text = draft.notes;
        _recipientEmail.text = draft.recipientEmail;
        _withholdingRate = draft.withholdingRate;
        _lines = draft.lines.isEmpty
            ? [_LineData()]
            : draft.lines
                  .map(
                    (l) => _LineData(
                      description: l.description,
                      quantity: l.quantity,
                      unitPrice: l.unitPrice,
                      discountPercent: l.discountPercent,
                      vatRate: l.vatRate,
                    ),
                  )
                  .toList();
        _loading = false;
      });
    } catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(
          context,
        ).showSnackBar(SnackBar(content: Text(apiErrorMessage(e))));
        context.pop();
      }
    }
  }

  @override
  void dispose() {
    _invoiceDate.dispose();
    _paymentMethod.dispose();
    _notes.dispose();
    _recipientEmail.dispose();
    super.dispose();
  }

  Map<String, dynamic> _buildPayload() {
    return {
      'customer_id': _customerId ?? '',
      'invoice_date': _invoiceDate.text.trim(),
      'payment_method': _paymentMethod.text.trim(),
      'notes': _notes.text.trim(),
      'recipient_email': _recipientEmail.text.trim(),
      'withholding_rate': _withholdingRate,
      'lines': _lines
          .where((l) => l.description.isNotEmpty)
          .map((l) => l.toJson())
          .toList(),
    };
  }

  Future<void> _save() async {
    if (!_formKey.currentState!.validate()) return;
    if (_customerId == null) {
      ScaffoldMessenger.of(
        context,
      ).showSnackBar(const SnackBar(content: Text('Selecciona un cliente')));
      return;
    }
    setState(() => _saving = true);
    try {
      final repo = ref.read(invoicingRepositoryProvider);
      final payload = _buildPayload();
      if (_isEdit) {
        await repo.updateDraft(widget.draftId!, payload);
      } else {
        await repo.createDraft(payload);
      }
      ref.invalidate(invoiceDraftsProvider);
      if (mounted) context.pop();
    } catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(
          context,
        ).showSnackBar(SnackBar(content: Text(apiErrorMessage(e))));
      }
    } finally {
      if (mounted) setState(() => _saving = false);
    }
  }

  Future<void> _deleteDraft() async {
    if (!_isEdit) return;
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('Eliminar borrador'),
        content: const Text('Esta accion no se puede deshacer.'),
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
            child: const Text('Eliminar'),
          ),
        ],
      ),
    );
    if (confirmed != true) return;
    try {
      await ref.read(invoicingRepositoryProvider).deleteDraft(widget.draftId!);
      ref.invalidate(invoiceDraftsProvider);
      if (mounted) context.pop();
    } catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(
          context,
        ).showSnackBar(SnackBar(content: Text(apiErrorMessage(e))));
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    if (_loading) {
      return Scaffold(
        appBar: AppBar(
          title: Text(_isEdit ? 'Editar borrador' : 'Nueva factura'),
        ),
        body: const Center(child: CircularProgressIndicator()),
      );
    }

    return Scaffold(
      appBar: AppBar(
        title: Text(_isEdit ? 'Editar borrador' : 'Nueva factura'),
        actions: [
          if (_isEdit)
            IconButton(
              icon: const Icon(Icons.delete_outline),
              tooltip: 'Eliminar borrador',
              onPressed: _deleteDraft,
            ),
          if (_isEdit)
            TextButton(
              onPressed: () =>
                  context.push('/invoicing/drafts/${widget.draftId}/issue'),
              child: const Text('Emitir'),
            ),
        ],
      ),
      body: Form(
        key: _formKey,
        child: ListView(
          padding: const EdgeInsets.all(16),
          children: [
            // Customer selector
            _CustomerSelector(
              selectedId: _customerId,
              onChanged: (id) => setState(() => _customerId = id),
            ),
            const SizedBox(height: 12),

            // Date
            TextFormField(
              controller: _invoiceDate,
              decoration: const InputDecoration(
                labelText: 'Fecha de factura',
                hintText: 'YYYY-MM-DD',
              ),
            ),
            const SizedBox(height: 12),

            // Payment method
            TextFormField(
              controller: _paymentMethod,
              decoration: const InputDecoration(
                labelText: 'Forma de pago',
                hintText: 'Ej: Transferencia bancaria',
              ),
            ),
            const SizedBox(height: 12),

            // Withholding
            DropdownButtonFormField<String>(
              initialValue: _withholdingRate,
              decoration: const InputDecoration(labelText: 'Retencion IRPF'),
              items: const [
                DropdownMenuItem(value: '0', child: Text('Sin retencion')),
                DropdownMenuItem(value: '7', child: Text('7%')),
                DropdownMenuItem(value: '15', child: Text('15%')),
                DropdownMenuItem(value: '19', child: Text('19%')),
              ],
              onChanged: (v) {
                if (v != null) setState(() => _withholdingRate = v);
              },
            ),
            const SizedBox(height: 16),

            // Lines header
            Row(
              mainAxisAlignment: MainAxisAlignment.spaceBetween,
              children: [
                Text('Lineas', style: Theme.of(context).textTheme.titleMedium),
                IconButton(
                  icon: const Icon(Icons.add_circle_outline),
                  tooltip: 'Anadir linea',
                  onPressed: () => setState(() => _lines.add(_LineData())),
                ),
              ],
            ),
            const SizedBox(height: 8),

            // Lines
            for (var i = 0; i < _lines.length; i++)
              _LineEditor(
                key: ValueKey('line-$i'),
                data: _lines[i],
                index: i,
                canRemove: _lines.length > 1,
                onRemove: () => setState(() => _lines.removeAt(i)),
              ),

            const SizedBox(height: 12),

            // Notes
            TextFormField(
              controller: _notes,
              decoration: const InputDecoration(labelText: 'Notas'),
              maxLines: 3,
            ),
            const SizedBox(height: 12),

            // Recipient email
            TextFormField(
              controller: _recipientEmail,
              decoration: const InputDecoration(
                labelText: 'Email destinatario',
                hintText: 'Para envio automatico del PDF',
              ),
              keyboardType: TextInputType.emailAddress,
            ),
            const SizedBox(height: 24),

            // Save button
            FilledButton(
              onPressed: _saving ? null : _save,
              child: _saving
                  ? const SizedBox(
                      height: 20,
                      width: 20,
                      child: CircularProgressIndicator(strokeWidth: 2),
                    )
                  : Text(_isEdit ? 'Guardar cambios' : 'Crear borrador'),
            ),
          ],
        ),
      ),
    );
  }
}

/// Selector de cliente con dropdown.
class _CustomerSelector extends ConsumerWidget {
  const _CustomerSelector({required this.selectedId, required this.onChanged});

  final String? selectedId;
  final ValueChanged<String?> onChanged;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final customersAsync = ref.watch(invoiceCustomersProvider);

    return customersAsync.when(
      loading: () => const LinearProgressIndicator(),
      error: (e, _) => Text('Error cargando clientes: ${apiErrorMessage(e)}'),
      data: (customers) {
        if (customers.isEmpty) {
          return OutlinedButton.icon(
            onPressed: () async {
              final created = await context.push<bool>(
                '/invoicing/customers/new',
              );
              if (created == true) {
                ref.invalidate(invoiceCustomersProvider);
              }
            },
            icon: const Icon(Icons.person_add),
            label: const Text('Crear primer cliente'),
          );
        }
        return DropdownButtonFormField<String>(
          initialValue: customers.any((c) => c.id == selectedId)
              ? selectedId
              : null,
          decoration: const InputDecoration(labelText: 'Cliente *'),
          items: customers
              .map(
                (c) => DropdownMenuItem(
                  value: c.id,
                  child: Text('${c.legalName} (${c.taxId})'),
                ),
              )
              .toList(),
          onChanged: onChanged,
          validator: (v) =>
              v == null || v.isEmpty ? 'Selecciona un cliente' : null,
        );
      },
    );
  }
}

/// Editor de una linea de factura.
class _LineEditor extends StatelessWidget {
  const _LineEditor({
    super.key,
    required this.data,
    required this.index,
    required this.canRemove,
    required this.onRemove,
  });

  final _LineData data;
  final int index;
  final bool canRemove;
  final VoidCallback onRemove;

  @override
  Widget build(BuildContext context) {
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
                const Spacer(),
                if (canRemove)
                  IconButton(
                    icon: const Icon(Icons.remove_circle_outline, size: 20),
                    onPressed: onRemove,
                  ),
              ],
            ),
            TextFormField(
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
                      labelText: 'Precio unitario',
                    ),
                    keyboardType: const TextInputType.numberWithOptions(
                      decimal: true,
                    ),
                    onChanged: (v) => data.unitPrice = v,
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

/// Datos mutables de una linea de factura en edicion.
class _LineData {
  String description;
  String quantity;
  String unitPrice;
  String discountPercent;
  String vatRate;

  _LineData({
    this.description = '',
    this.quantity = '1',
    this.unitPrice = '0',
    this.discountPercent = '0',
    this.vatRate = '21.00',
  });

  Map<String, dynamic> toJson() => {
    'description': description,
    'quantity': quantity,
    'unit_price': unitPrice,
    'discount_percent': discountPercent,
    'vat_rate': vatRate,
  };
}
