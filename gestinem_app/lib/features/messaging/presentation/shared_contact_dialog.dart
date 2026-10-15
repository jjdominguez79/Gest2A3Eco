import 'package:flutter/material.dart';

import '../domain/message.dart';
import 'selector_contacto_nativo_stub.dart'
    if (dart.library.io) 'selector_contacto_nativo.dart';

Future<SharedContact?> seleccionarContactoCompartido(
  BuildContext context,
) async {
  if (!selectorContactoNativoDisponible) {
    return _mostrarFormularioContacto(context);
  }

  try {
    final contacto = await seleccionarContactoNativo();
    if (contacto == null || !context.mounted) return null;
    return await _confirmarContacto(context, contacto);
  } catch (error) {
    debugPrint('No se pudo abrir el selector nativo de contactos: $error');
    if (!context.mounted) return null;
    ScaffoldMessenger.of(context).showSnackBar(
      const SnackBar(
        content: Text(
          'No se pudo abrir la agenda. Puedes introducir el contacto manualmente.',
        ),
      ),
    );
    return _mostrarFormularioContacto(context);
  }
}

Future<SharedContact?> _confirmarContacto(
  BuildContext context,
  SharedContact contacto,
) {
  return showDialog<SharedContact>(
    context: context,
    builder: (context) => AlertDialog(
      title: const Text('Compartir contacto'),
      content: ListTile(
        contentPadding: EdgeInsets.zero,
        leading: const CircleAvatar(child: Icon(Icons.person_outline)),
        title: Text(contacto.name),
        subtitle: Text(contacto.phone),
      ),
      actions: [
        TextButton(
          onPressed: () => Navigator.pop(context),
          child: const Text('Cancelar'),
        ),
        FilledButton.icon(
          key: const Key('share-selected-contact'),
          onPressed: () => Navigator.pop(context, contacto),
          icon: const Icon(Icons.send),
          label: const Text('Compartir'),
        ),
      ],
    ),
  );
}

Future<SharedContact?> _mostrarFormularioContacto(BuildContext context) {
  return showDialog<SharedContact>(
    context: context,
    builder: (_) => const _SharedContactDialog(),
  );
}

class _SharedContactDialog extends StatefulWidget {
  const _SharedContactDialog();

  @override
  State<_SharedContactDialog> createState() => _SharedContactDialogState();
}

class _SharedContactDialogState extends State<_SharedContactDialog> {
  final _formKey = GlobalKey<FormState>();
  final _name = TextEditingController();
  final _phone = TextEditingController();
  final _email = TextEditingController();
  final _organization = TextEditingController();

  @override
  void dispose() {
    _name.dispose();
    _phone.dispose();
    _email.dispose();
    _organization.dispose();
    super.dispose();
  }

  void _submit() {
    if (!_formKey.currentState!.validate()) return;
    Navigator.pop(
      context,
      SharedContact(
        name: _name.text.trim(),
        phone: _phone.text.trim(),
        email: _email.text.trim().toLowerCase(),
        organization: _organization.text.trim(),
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    return AlertDialog(
      title: const Text('Compartir contacto'),
      content: Form(
        key: _formKey,
        child: SingleChildScrollView(
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              TextFormField(
                key: const Key('shared-contact-name'),
                controller: _name,
                autofocus: true,
                textCapitalization: TextCapitalization.words,
                decoration: const InputDecoration(
                  labelText: 'Nombre *',
                  prefixIcon: Icon(Icons.person_outline),
                ),
                validator: (value) => value == null || value.trim().isEmpty
                    ? 'Indica el nombre'
                    : null,
              ),
              TextFormField(
                key: const Key('shared-contact-organization'),
                controller: _organization,
                textCapitalization: TextCapitalization.words,
                decoration: const InputDecoration(
                  labelText: 'Empresa',
                  prefixIcon: Icon(Icons.business_outlined),
                ),
              ),
              TextFormField(
                key: const Key('shared-contact-phone'),
                controller: _phone,
                keyboardType: TextInputType.phone,
                decoration: const InputDecoration(
                  labelText: 'Teléfono',
                  prefixIcon: Icon(Icons.phone_outlined),
                ),
                validator: (_) =>
                    _phone.text.trim().isEmpty && _email.text.trim().isEmpty
                    ? 'Indica un teléfono o un email'
                    : null,
              ),
              TextFormField(
                key: const Key('shared-contact-email'),
                controller: _email,
                keyboardType: TextInputType.emailAddress,
                decoration: const InputDecoration(
                  labelText: 'Email',
                  prefixIcon: Icon(Icons.email_outlined),
                ),
                validator: (value) {
                  final email = value?.trim() ?? '';
                  if (email.isEmpty) return null;
                  return RegExp(r'^[^@\s]+@[^@\s]+\.[^@\s]+$').hasMatch(email)
                      ? null
                      : 'Email no válido';
                },
                onFieldSubmitted: (_) => _submit(),
              ),
            ],
          ),
        ),
      ),
      actions: [
        TextButton(
          onPressed: () => Navigator.pop(context),
          child: const Text('Cancelar'),
        ),
        FilledButton.icon(
          key: const Key('share-contact-submit'),
          onPressed: _submit,
          icon: const Icon(Icons.send),
          label: const Text('Compartir'),
        ),
      ],
    );
  }
}
