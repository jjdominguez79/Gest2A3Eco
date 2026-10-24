import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../../core/api/api_client.dart';
import 'invoicing_providers.dart';

/// Formulario de alta/edicion de un articulo del catalogo.
class CatalogFormScreen extends ConsumerStatefulWidget {
  const CatalogFormScreen({super.key, this.itemId});

  final String? itemId;

  @override
  ConsumerState<CatalogFormScreen> createState() => _CatalogFormScreenState();
}

class _CatalogFormScreenState extends ConsumerState<CatalogFormScreen> {
  final _formKey = GlobalKey<FormState>();
  bool _loading = true;
  bool _saving = false;
  bool _active = true;

  String _itemType = 'service';
  final _code = TextEditingController();
  final _description = TextEditingController();
  final _unit = TextEditingController();
  final _unitPrice = TextEditingController(text: '0');
  String _vatRate = '21.00';
  final _withholdingRate = TextEditingController(text: '0');

  bool get _isEdit => widget.itemId != null;

  @override
  void initState() {
    super.initState();
    if (_isEdit) {
      _load();
    } else {
      _loading = false;
    }
  }

  Future<void> _load() async {
    try {
      final item = await ref
          .read(invoicingRepositoryProvider)
          .getCatalogItem(widget.itemId!);
      if (!mounted) return;
      setState(() {
        _itemType = item.itemType;
        _code.text = item.code;
        _description.text = item.description;
        _unit.text = item.unit;
        _unitPrice.text = item.unitPrice;
        _vatRate = item.vatRate;
        _withholdingRate.text = item.withholdingRate;
        _active = item.active;
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
    _code.dispose();
    _description.dispose();
    _unit.dispose();
    _unitPrice.dispose();
    _withholdingRate.dispose();
    super.dispose();
  }

  Future<void> _save() async {
    if (!_formKey.currentState!.validate()) return;
    setState(() => _saving = true);
    final payload = {
      'item_type': _itemType,
      'code': _code.text.trim(),
      'description': _description.text.trim(),
      'unit': _unit.text.trim(),
      'unit_price': _unitPrice.text.trim(),
      'vat_rate': _vatRate,
      'withholding_rate': _withholdingRate.text.trim(),
      if (_isEdit) 'active': _active,
    };
    try {
      final repo = ref.read(invoicingRepositoryProvider);
      if (_isEdit) {
        await repo.updateCatalogItem(widget.itemId!, payload);
      } else {
        await repo.createCatalogItem(payload);
      }
      if (mounted) context.pop(true);
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

  Future<void> _deactivate() async {
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('Dar de baja el articulo'),
        content: const Text(
          'Dejara de aparecer para anadirlo a nuevas facturas. Las facturas '
          'ya emitidas con este articulo no se ven afectadas.',
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(ctx, false),
            child: const Text('Cancelar'),
          ),
          FilledButton(
            onPressed: () => Navigator.pop(ctx, true),
            child: const Text('Dar de baja'),
          ),
        ],
      ),
    );
    if (confirmed != true) return;
    try {
      await ref
          .read(invoicingRepositoryProvider)
          .deactivateCatalogItem(widget.itemId!);
      if (mounted) context.pop(true);
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
        appBar: AppBar(title: const Text('Articulo')),
        body: const Center(child: CircularProgressIndicator()),
      );
    }

    return Scaffold(
      appBar: AppBar(
        title: Text(_isEdit ? 'Editar articulo' : 'Nuevo articulo'),
        actions: [
          if (_isEdit && _active)
            IconButton(
              icon: const Icon(Icons.archive_outlined),
              tooltip: 'Dar de baja',
              onPressed: _deactivate,
            ),
        ],
      ),
      body: Form(
        key: _formKey,
        child: ListView(
          padding: const EdgeInsets.all(16),
          children: [
            SegmentedButton<String>(
              segments: const [
                ButtonSegment(value: 'service', label: Text('Servicio')),
                ButtonSegment(value: 'product', label: Text('Producto')),
              ],
              selected: {_itemType},
              onSelectionChanged: (s) => setState(() => _itemType = s.first),
            ),
            const SizedBox(height: 16),
            TextFormField(
              controller: _description,
              decoration: const InputDecoration(labelText: 'Descripcion *'),
              validator: (v) =>
                  v == null || v.trim().isEmpty ? 'Obligatoria' : null,
            ),
            const SizedBox(height: 12),
            TextFormField(
              controller: _code,
              decoration: const InputDecoration(
                labelText: 'Codigo / SKU (opcional)',
              ),
            ),
            const SizedBox(height: 12),
            TextFormField(
              controller: _unit,
              decoration: const InputDecoration(
                labelText: 'Unidad (ej: hora, ud, mes)',
              ),
            ),
            const SizedBox(height: 12),
            Row(
              children: [
                Expanded(
                  child: TextFormField(
                    controller: _unitPrice,
                    decoration: const InputDecoration(labelText: 'Precio *'),
                    keyboardType: const TextInputType.numberWithOptions(
                      decimal: true,
                    ),
                    validator: (v) =>
                        v == null || v.trim().isEmpty ? 'Obligatorio' : null,
                  ),
                ),
                const SizedBox(width: 8),
                Expanded(
                  child: DropdownButtonFormField<String>(
                    initialValue: _vatRate,
                    decoration: const InputDecoration(labelText: 'IVA %'),
                    items: const [
                      DropdownMenuItem(value: '0', child: Text('0%')),
                      DropdownMenuItem(value: '4.00', child: Text('4%')),
                      DropdownMenuItem(value: '10.00', child: Text('10%')),
                      DropdownMenuItem(value: '21.00', child: Text('21%')),
                    ],
                    onChanged: (v) {
                      if (v != null) setState(() => _vatRate = v);
                    },
                  ),
                ),
              ],
            ),
            const SizedBox(height: 12),
            TextFormField(
              controller: _withholdingRate,
              decoration: const InputDecoration(
                labelText: 'Retencion sugerida % (opcional)',
              ),
              keyboardType: const TextInputType.numberWithOptions(
                decimal: true,
              ),
            ),
            const SizedBox(height: 24),
            FilledButton(
              onPressed: _saving ? null : _save,
              child: _saving
                  ? const SizedBox(
                      height: 20,
                      width: 20,
                      child: CircularProgressIndicator(strokeWidth: 2),
                    )
                  : Text(_isEdit ? 'Guardar cambios' : 'Crear articulo'),
            ),
          ],
        ),
      ),
    );
  }
}
