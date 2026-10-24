import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../../core/api/api_client.dart';
import 'invoice_line_editor.dart';
import 'invoicing_providers.dart';

/// Crea una factura rectificativa a partir de una factura ya emitida.
///
/// La factura original nunca se edita (seccion 15: una factura emitida no
/// se modifica). Este formulario crea un documento nuevo que la referencia.
class RectifyInvoiceScreen extends ConsumerStatefulWidget {
  const RectifyInvoiceScreen({super.key, required this.invoiceId});

  final String invoiceId;

  @override
  ConsumerState<RectifyInvoiceScreen> createState() =>
      _RectifyInvoiceScreenState();
}

class _RectifyInvoiceScreenState extends ConsumerState<RectifyInvoiceScreen> {
  final _formKey = GlobalKey<FormState>();
  final _reason = TextEditingController();
  List<InvoiceLineData> _lines = [InvoiceLineData()];
  bool _initialized = false;
  bool _saving = false;

  @override
  void dispose() {
    _reason.dispose();
    super.dispose();
  }

  void _initializeFromOriginal(List<dynamic> originalLines) {
    if (_initialized) return;
    _initialized = true;
    if (originalLines.isNotEmpty) {
      _lines = originalLines
          .map(
            (l) => InvoiceLineData(
              description: l.description as String,
              quantity: l.quantity as String,
              unitPrice: l.unitPrice as String,
              discountPercent: l.discountPercent as String,
              vatRate: l.vatRate as String,
            ),
          )
          .toList();
    }
  }

  Future<void> _submit() async {
    if (!_formKey.currentState!.validate()) return;
    if (_reason.text.trim().isEmpty) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('Indica el motivo de la rectificacion')),
      );
      return;
    }
    setState(() => _saving = true);
    try {
      final repo = ref.read(invoicingRepositoryProvider);
      final rectification = await repo.rectifyInvoice(
        widget.invoiceId,
        reason: _reason.text.trim(),
        lines: _lines
            .where((l) => l.description.isNotEmpty)
            .map((l) => l.toJson())
            .toList(),
      );
      ref.invalidate(invoiceDetailProvider(widget.invoiceId));
      ref.invalidate(invoiceListProvider);
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(
            content: Text(
              'Rectificativa ${rectification.displayNumber} creada',
            ),
          ),
        );
        context.go('/invoicing/invoices/${rectification.id}');
      }
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

  @override
  Widget build(BuildContext context) {
    final originalAsync = ref.watch(invoiceDetailProvider(widget.invoiceId));

    return Scaffold(
      appBar: AppBar(title: const Text('Factura rectificativa')),
      body: originalAsync.when(
        loading: () => const Center(child: CircularProgressIndicator()),
        error: (e, _) => Center(child: Text('Error: ${apiErrorMessage(e)}')),
        data: (original) {
          _initializeFromOriginal(original.lines);
          return Form(
            key: _formKey,
            child: ListView(
              padding: const EdgeInsets.all(16),
              children: [
                Card(
                  color: Colors.amber.shade50,
                  child: Padding(
                    padding: const EdgeInsets.all(16),
                    child: Text(
                      'Rectifica la factura ${original.displayNumber}. '
                      'La factura original no se modifica: se emitira un '
                      'documento nuevo que la referencia.',
                    ),
                  ),
                ),
                const SizedBox(height: 16),
                TextFormField(
                  controller: _reason,
                  decoration: const InputDecoration(
                    labelText: 'Motivo de la rectificacion *',
                  ),
                  maxLines: 2,
                  validator: (v) => v == null || v.trim().isEmpty
                      ? 'El motivo es obligatorio'
                      : null,
                ),
                const SizedBox(height: 16),
                Row(
                  mainAxisAlignment: MainAxisAlignment.spaceBetween,
                  children: [
                    Text(
                      'Lineas corregidas',
                      style: Theme.of(context).textTheme.titleMedium,
                    ),
                    IconButton(
                      icon: const Icon(Icons.add_circle_outline),
                      onPressed: () =>
                          setState(() => _lines.add(InvoiceLineData())),
                    ),
                  ],
                ),
                for (var i = 0; i < _lines.length; i++)
                  InvoiceLineEditor(
                    key: ValueKey('rect-line-$i'),
                    data: _lines[i],
                    index: i,
                    canRemove: _lines.length > 1,
                    onRemove: () => setState(() => _lines.removeAt(i)),
                    onChanged: () => setState(() {}),
                  ),
                const SizedBox(height: 24),
                FilledButton.icon(
                  onPressed: _saving ? null : _submit,
                  icon: _saving
                      ? const SizedBox(
                          height: 18,
                          width: 18,
                          child: CircularProgressIndicator(strokeWidth: 2),
                        )
                      : const Icon(Icons.send),
                  label: const Text('Emitir rectificativa'),
                ),
              ],
            ),
          );
        },
      ),
    );
  }
}
