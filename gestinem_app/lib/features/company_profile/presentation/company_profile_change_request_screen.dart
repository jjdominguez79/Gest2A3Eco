import 'package:file_picker/file_picker.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../../core/api/api_client.dart';
import '../../../core/validation/email_validation.dart';
import '../domain/company_profile.dart';
import 'company_profile_providers.dart';

class CompanyProfileChangeRequestScreen extends ConsumerWidget {
  const CompanyProfileChangeRequestScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final profile = ref.watch(companyProfileProvider);
    return Scaffold(
      appBar: AppBar(title: const Text('Solicitar cambios')),
      body: SafeArea(
        top: false,
        child: profile.when(
          loading: () => const Center(child: CircularProgressIndicator()),
          error: (error, _) => Center(
            child: Text(
              'No se pudo cargar la ficha: ${apiErrorMessage(error)}',
            ),
          ),
          data: (value) => _ChangeRequestForm(profile: value),
        ),
      ),
    );
  }
}

class _ChangeRequestForm extends ConsumerStatefulWidget {
  const _ChangeRequestForm({required this.profile});

  final CompanyProfile profile;

  @override
  ConsumerState<_ChangeRequestForm> createState() => _ChangeRequestFormState();
}

class _ChangeRequestFormState extends ConsumerState<_ChangeRequestForm> {
  final _formKey = GlobalKey<FormState>();
  late final Map<String, TextEditingController> _fields;
  final _bankAccounts = TextEditingController();
  final _notes = TextEditingController();
  PlatformFile? _logo;
  bool _sending = false;

  static final _upper = TextInputFormatter.withFunction(
    (oldValue, newValue) => newValue.copyWith(
      text: newValue.text.toUpperCase(),
      selection: newValue.selection,
      composing: TextRange.empty,
    ),
  );

  @override
  void initState() {
    super.initState();
    final profile = widget.profile;
    _fields = {
      'legal_name': TextEditingController(
        text: profile.legalName ?? profile.name,
      ),
      'tax_id': TextEditingController(text: profile.taxId ?? ''),
      'address': TextEditingController(text: profile.address ?? ''),
      'postal_code': TextEditingController(text: profile.postalCode ?? ''),
      'city': TextEditingController(text: profile.city ?? ''),
      'province': TextEditingController(text: profile.province ?? ''),
      'country': TextEditingController(text: profile.country ?? 'ES'),
      'phone': TextEditingController(text: profile.phone ?? ''),
      'email': TextEditingController(text: profile.email ?? ''),
    };
  }

  @override
  void dispose() {
    for (final controller in _fields.values) {
      controller.dispose();
    }
    _bankAccounts.dispose();
    _notes.dispose();
    super.dispose();
  }

  String _original(String field) => switch (field) {
    'legal_name' => widget.profile.legalName ?? widget.profile.name,
    'tax_id' => widget.profile.taxId ?? '',
    'address' => widget.profile.address ?? '',
    'postal_code' => widget.profile.postalCode ?? '',
    'city' => widget.profile.city ?? '',
    'province' => widget.profile.province ?? '',
    'country' => widget.profile.country ?? 'ES',
    'phone' => widget.profile.phone ?? '',
    'email' => widget.profile.email ?? '',
    _ => '',
  };

  Future<void> _pickLogo() async {
    final result = await FilePicker.pickFiles(
      type: FileType.custom,
      allowedExtensions: const ['png', 'jpg', 'jpeg', 'webp'],
    );
    if (result.isNotEmpty && mounted) {
      setState(() => _logo = result.single);
    }
  }

  Future<void> _submit() async {
    if (!_formKey.currentState!.validate() || _sending) return;
    final changes = <String, dynamic>{};
    for (final entry in _fields.entries) {
      final value = entry.value.text.trim();
      if (value != _original(entry.key).trim()) changes[entry.key] = value;
    }
    final accounts = _bankAccounts.text
        .split(RegExp(r'[\r\n,;]+'))
        .map((value) => value.replaceAll(RegExp(r'\s+'), '').toUpperCase())
        .where((value) => value.isNotEmpty)
        .toList(growable: false);
    if (accounts.isNotEmpty) changes['bank_accounts'] = accounts;
    if (changes.isEmpty && _logo == null) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(
          content: Text('Modifica algún dato o añade un logotipo.'),
        ),
      );
      return;
    }
    setState(() => _sending = true);
    try {
      await ref
          .read(companyProfileRepositoryProvider)
          .requestChanges(changes: changes, notes: _notes.text, logo: _logo);
      ref.invalidate(profileChangeRequestsProvider);
      if (!mounted) return;
      await showDialog<void>(
        context: context,
        builder: (dialogContext) => AlertDialog(
          title: const Text('Solicitud enviada'),
          content: const Text(
            'El despacho ha recibido el aviso. Los datos actuales no cambiarán hasta que se revise la solicitud.',
          ),
          actions: [
            FilledButton(
              onPressed: () => Navigator.pop(dialogContext),
              child: const Text('Aceptar'),
            ),
          ],
        ),
      );
      if (mounted) context.pop();
    } catch (error) {
      if (mounted) {
        ScaffoldMessenger.of(
          context,
        ).showSnackBar(SnackBar(content: Text(apiErrorMessage(error))));
      }
    } finally {
      if (mounted) setState(() => _sending = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    return Form(
      key: _formKey,
      child: ListView(
        padding: const EdgeInsets.all(16),
        children: [
          const Text(
            'Indica únicamente los cambios que deseas solicitar. El despacho los revisará antes de actualizar tu ficha.',
          ),
          const SizedBox(height: 16),
          _field('legal_name', 'Razón social', upper: true),
          _field('tax_id', 'NIF/CIF', upper: true),
          _field('address', 'Dirección', upper: true),
          Row(
            children: [
              Expanded(child: _field('postal_code', 'Código postal')),
              const SizedBox(width: 12),
              Expanded(child: _field('city', 'Población', upper: true)),
            ],
          ),
          _field('province', 'Provincia', upper: true),
          _field('country', 'País', upper: true),
          _field('phone', 'Teléfono', keyboardType: TextInputType.phone),
          _field(
            'email',
            'Correo electrónico',
            keyboardType: TextInputType.emailAddress,
            validator: (value) => value.trim().isEmpty || isValidEmail(value)
                ? null
                : 'Indica un correo válido',
          ),
          TextFormField(
            key: const Key('profile-change-bank-accounts'),
            controller: _bankAccounts,
            textCapitalization: TextCapitalization.characters,
            inputFormatters: [_upper],
            maxLines: 3,
            decoration: const InputDecoration(
              labelText: 'Añadir cuentas bancarias',
              hintText: 'Una cuenta IBAN por línea',
            ),
          ),
          const SizedBox(height: 12),
          OutlinedButton.icon(
            key: const Key('profile-change-logo'),
            onPressed: _pickLogo,
            icon: const Icon(Icons.image_outlined),
            label: Text(_logo?.name ?? 'Añadir o cambiar logotipo'),
          ),
          const SizedBox(height: 12),
          TextFormField(
            controller: _notes,
            maxLines: 3,
            maxLength: 2000,
            decoration: const InputDecoration(
              labelText: 'Observaciones para el despacho',
            ),
          ),
          const SizedBox(height: 16),
          FilledButton.icon(
            key: const Key('send-profile-change-request'),
            onPressed: _sending ? null : _submit,
            icon: _sending
                ? const SizedBox.square(
                    dimension: 18,
                    child: CircularProgressIndicator(strokeWidth: 2),
                  )
                : const Icon(Icons.send_outlined),
            label: const Text('Enviar solicitud'),
          ),
        ],
      ),
    );
  }

  Widget _field(
    String name,
    String label, {
    bool upper = false,
    TextInputType? keyboardType,
    String? Function(String value)? validator,
  }) {
    return Padding(
      padding: const EdgeInsets.only(bottom: 12),
      child: TextFormField(
        key: Key('profile-change-$name'),
        controller: _fields[name],
        textCapitalization: upper
            ? TextCapitalization.characters
            : TextCapitalization.none,
        inputFormatters: upper ? [_upper] : null,
        keyboardType: keyboardType,
        validator: validator == null ? null : (value) => validator(value ?? ''),
        decoration: InputDecoration(labelText: label),
      ),
    );
  }
}
