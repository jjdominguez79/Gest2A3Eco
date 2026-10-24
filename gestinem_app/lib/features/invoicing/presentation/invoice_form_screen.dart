import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../../core/api/api_client.dart';
import 'invoice_line_editor.dart';
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

  List<InvoiceLineData> _lines = [InvoiceLineData()];

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
            ? [InvoiceLineData()]
            : draft.lines
                  .map(
                    (l) => InvoiceLineData(
                      description: l.description,
                      quantity: l.quantity,
                      unitPrice: l.unitPrice,
                      discountPercent: l.discountPercent,
                      vatRate: l.vatRate,
                      catalogItemId: l.catalogItemId,
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
                  onPressed: () =>
                      setState(() => _lines.add(InvoiceLineData())),
                ),
              ],
            ),
            const SizedBox(height: 8),

            // Lines
            for (var i = 0; i < _lines.length; i++)
              InvoiceLineEditor(
                key: ValueKey('line-$i'),
                data: _lines[i],
                index: i,
                canRemove: _lines.length > 1,
                onRemove: () => setState(() => _lines.removeAt(i)),
                onChanged: () => setState(() {}),
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
