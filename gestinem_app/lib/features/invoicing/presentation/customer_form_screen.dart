import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../../core/api/api_client.dart';
import 'invoicing_providers.dart';

/// Formulario para crear un nuevo cliente de facturacion.
class CustomerFormScreen extends ConsumerStatefulWidget {
  const CustomerFormScreen({super.key});

  @override
  ConsumerState<CustomerFormScreen> createState() => _CustomerFormScreenState();
}

class _CustomerFormScreenState extends ConsumerState<CustomerFormScreen> {
  final _formKey = GlobalKey<FormState>();
  final _taxId = TextEditingController();
  final _legalName = TextEditingController();
  final _address = TextEditingController();
  final _postalCode = TextEditingController();
  final _city = TextEditingController();
  final _province = TextEditingController();
  final _email = TextEditingController();
  final _phone = TextEditingController();
  String _country = 'ES';
  bool _saving = false;

  @override
  void dispose() {
    _taxId.dispose();
    _legalName.dispose();
    _address.dispose();
    _postalCode.dispose();
    _city.dispose();
    _province.dispose();
    _email.dispose();
    _phone.dispose();
    super.dispose();
  }

  Future<void> _save() async {
    if (!_formKey.currentState!.validate()) return;
    setState(() => _saving = true);
    try {
      final repo = ref.read(invoicingRepositoryProvider);
      await repo.createCustomer({
        'tax_id': _taxId.text.trim(),
        'legal_name': _legalName.text.trim(),
        'address': _address.text.trim(),
        'postal_code': _postalCode.text.trim(),
        'city': _city.text.trim(),
        'province': _province.text.trim(),
        'country': _country,
        'email': _email.text.trim(),
        'phone': _phone.text.trim(),
      });
      if (mounted) {
        context.pop(true);
      }
    } catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text(apiErrorMessage(e))),
        );
      }
    } finally {
      if (mounted) setState(() => _saving = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('Nuevo cliente')),
      body: SingleChildScrollView(
        padding: const EdgeInsets.all(16),
        child: Form(
          key: _formKey,
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              TextFormField(
                controller: _taxId,
                decoration: const InputDecoration(
                  labelText: 'NIF/CIF *',
                  hintText: 'Ej: B12345678',
                ),
                textCapitalization: TextCapitalization.characters,
                validator: (v) {
                  if (v == null || v.trim().isEmpty) {
                    return 'El NIF/CIF es obligatorio';
                  }
                  final id = v.trim().toUpperCase();
                  if (id.length < 8 || id.length > 9) {
                    return 'Formato de NIF/CIF no valido';
                  }
                  return null;
                },
              ),
              const SizedBox(height: 12),
              TextFormField(
                controller: _legalName,
                decoration:
                    const InputDecoration(labelText: 'Razon social *'),
                validator: (v) => v == null || v.trim().isEmpty
                    ? 'La razon social es obligatoria'
                    : null,
              ),
              const SizedBox(height: 12),
              TextFormField(
                controller: _address,
                decoration: const InputDecoration(labelText: 'Direccion'),
              ),
              const SizedBox(height: 12),
              Row(
                children: [
                  Expanded(
                    flex: 2,
                    child: TextFormField(
                      controller: _postalCode,
                      decoration:
                          const InputDecoration(labelText: 'Codigo postal'),
                      keyboardType: TextInputType.number,
                    ),
                  ),
                  const SizedBox(width: 12),
                  Expanded(
                    flex: 3,
                    child: TextFormField(
                      controller: _city,
                      decoration:
                          const InputDecoration(labelText: 'Poblacion'),
                    ),
                  ),
                ],
              ),
              const SizedBox(height: 12),
              Row(
                children: [
                  Expanded(
                    child: TextFormField(
                      controller: _province,
                      decoration:
                          const InputDecoration(labelText: 'Provincia'),
                    ),
                  ),
                  const SizedBox(width: 12),
                  Expanded(
                    child: DropdownButtonFormField<String>(
                      initialValue: _country,
                      decoration: const InputDecoration(labelText: 'Pais'),
                      items: const [
                        DropdownMenuItem(value: 'ES', child: Text('Espana')),
                        DropdownMenuItem(value: 'PT', child: Text('Portugal')),
                        DropdownMenuItem(value: 'FR', child: Text('Francia')),
                        DropdownMenuItem(value: 'DE', child: Text('Alemania')),
                        DropdownMenuItem(value: 'IT', child: Text('Italia')),
                        DropdownMenuItem(value: 'GB', child: Text('Reino Unido')),
                      ],
                      onChanged: (v) {
                        if (v != null) setState(() => _country = v);
                      },
                    ),
                  ),
                ],
              ),
              const SizedBox(height: 12),
              TextFormField(
                controller: _email,
                decoration: const InputDecoration(labelText: 'Email'),
                keyboardType: TextInputType.emailAddress,
              ),
              const SizedBox(height: 12),
              TextFormField(
                controller: _phone,
                decoration: const InputDecoration(labelText: 'Telefono'),
                keyboardType: TextInputType.phone,
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
                    : const Text('Guardar cliente'),
              ),
            ],
          ),
        ),
      ),
    );
  }
}
