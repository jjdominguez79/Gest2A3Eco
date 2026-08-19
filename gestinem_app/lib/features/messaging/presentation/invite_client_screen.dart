import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../../core/api/api_client.dart';
import '../../auth/presentation/auth_controller.dart';
import '../domain/conversation.dart';
import 'messaging_providers.dart';

class InviteClientScreen extends ConsumerStatefulWidget {
  const InviteClientScreen({super.key});

  @override
  ConsumerState<InviteClientScreen> createState() => _InviteClientScreenState();
}

class _InviteClientScreenState extends ConsumerState<InviteClientScreen> {
  final _formKey = GlobalKey<FormState>();
  final _name = TextEditingController();
  final _email = TextEditingController();
  String _companyText = '';
  String? _selectedCompanyCode;
  bool _sendEmail = true;
  bool _sending = false;

  @override
  void dispose() {
    _name.dispose();
    _email.dispose();
    super.dispose();
  }

  String get _companyCode {
    final selected = _selectedCompanyCode;
    if (selected != null && selected.isNotEmpty) return selected;
    return _companyText.trim().split(RegExp(r'\s+|·')).first.toUpperCase();
  }

  Future<void> _submit() async {
    if (!_formKey.currentState!.validate() || _sending) return;
    setState(() => _sending = true);
    try {
      final result = await ref
          .read(messagingRepositoryProvider)
          .inviteClient(
            companyCode: _companyCode,
            name: _name.text.trim(),
            email: _email.text.trim(),
            sendEmail: _sendEmail,
          );
      ref.invalidate(conversationsProvider);
      if (!mounted) return;
      await _showResult(result);
      if (mounted) context.go('/');
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

  Future<void> _showResult(Map<String, dynamic> result) async {
    final url = result['url']?.toString() ?? '';
    final queued = result['email_queued'] == true;
    final expiresAt = DateTime.tryParse(result['expires_at']?.toString() ?? '');
    await showDialog<void>(
      context: context,
      builder: (dialogContext) => AlertDialog(
        title: Text(queued ? 'Invitación enviada' : 'Invitación creada'),
        content: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(
              queued
                  ? 'Se ha preparado el correo de invitación para ${_email.text.trim()}.'
                  : 'El correo automático no está disponible. Puedes copiar y enviar este enlace:',
            ),
            if (url.isNotEmpty) ...[
              const SizedBox(height: 12),
              SelectableText(url),
            ],
            if (expiresAt != null) ...[
              const SizedBox(height: 12),
              Text('Caduca: ${expiresAt.toLocal()}'),
            ],
          ],
        ),
        actions: [
          if (url.isNotEmpty)
            TextButton.icon(
              onPressed: () async {
                await Clipboard.setData(ClipboardData(text: url));
                if (dialogContext.mounted) {
                  ScaffoldMessenger.of(dialogContext).showSnackBar(
                    const SnackBar(content: Text('Enlace copiado')),
                  );
                }
              },
              icon: const Icon(Icons.copy_outlined),
              label: const Text('Copiar enlace'),
            ),
          FilledButton(
            onPressed: () => Navigator.pop(dialogContext),
            child: const Text('Aceptar'),
          ),
        ],
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    final profile = ref.watch(sessionProvider).valueOrNull!.profile;
    if (!profile.isAdmin) {
      return const Scaffold(
        body: Center(
          child: Text('Solo el administrador puede invitar clientes.'),
        ),
      );
    }
    final groups = groupConversationsByClient(
      ref.watch(conversationsProvider).valueOrNull ?? const [],
    );
    return Scaffold(
      appBar: AppBar(
        leading: IconButton(
          onPressed: () => context.go('/'),
          icon: const Icon(Icons.arrow_back),
        ),
        title: const Text('Invitar cliente'),
      ),
      body: Center(
        child: ConstrainedBox(
          constraints: const BoxConstraints(maxWidth: 620),
          child: Form(
            key: _formKey,
            child: ListView(
              padding: const EdgeInsets.all(24),
              children: [
                Text(
                  'Selecciona la empresa e indica la persona que utilizará Gestinem.',
                  style: Theme.of(context).textTheme.bodyLarge,
                ),
                const SizedBox(height: 20),
                Autocomplete<ClientGroup>(
                  displayStringForOption: (group) =>
                      '${group.companyCode} · ${group.displayName}',
                  optionsBuilder: (value) {
                    _companyText = value.text;
                    final query = value.text.trim().toLowerCase();
                    if (query.isEmpty) return groups.take(12);
                    return groups.where(
                      (group) =>
                          group.companyCode.toLowerCase().contains(query) ||
                          group.displayName.toLowerCase().contains(query),
                    );
                  },
                  onSelected: (group) {
                    _selectedCompanyCode = group.companyCode;
                    _companyText = group.companyCode;
                  },
                  fieldViewBuilder:
                      (context, controller, focusNode, onSubmit) =>
                          TextFormField(
                            key: const Key('invite-company'),
                            controller: controller,
                            focusNode: focusNode,
                            onChanged: (value) {
                              _companyText = value;
                              _selectedCompanyCode = null;
                            },
                            decoration: const InputDecoration(
                              labelText: 'Empresa',
                              hintText: 'E00006 o nombre del cliente',
                              prefixIcon: Icon(Icons.business_outlined),
                            ),
                            validator: (_) =>
                                RegExp(r'^E\d{5}$').hasMatch(_companyCode)
                                ? null
                                : 'Selecciona una empresa válida',
                          ),
                ),
                const SizedBox(height: 14),
                TextFormField(
                  key: const Key('invite-name'),
                  controller: _name,
                  textCapitalization: TextCapitalization.words,
                  decoration: const InputDecoration(
                    labelText: 'Nombre de la persona',
                    prefixIcon: Icon(Icons.person_outline),
                  ),
                  validator: (value) => (value ?? '').trim().isEmpty
                      ? 'Indica el nombre de la persona'
                      : null,
                ),
                const SizedBox(height: 14),
                TextFormField(
                  key: const Key('invite-email'),
                  controller: _email,
                  keyboardType: TextInputType.emailAddress,
                  decoration: const InputDecoration(
                    labelText: 'Correo electrónico',
                    prefixIcon: Icon(Icons.email_outlined),
                  ),
                  validator: (value) {
                    final email = (value ?? '').trim();
                    return email.contains('@') && email.contains('.')
                        ? null
                        : 'Indica un correo válido';
                  },
                ),
                const SizedBox(height: 8),
                SwitchListTile(
                  value: _sendEmail,
                  onChanged: (value) => setState(() => _sendEmail = value),
                  title: const Text('Enviar invitación por correo'),
                  subtitle: const Text(
                    'Siempre podrás copiar el enlace de invitación.',
                  ),
                ),
                const SizedBox(height: 20),
                FilledButton.icon(
                  key: const Key('send-invitation'),
                  onPressed: _sending ? null : _submit,
                  icon: _sending
                      ? const SizedBox.square(
                          dimension: 18,
                          child: CircularProgressIndicator(strokeWidth: 2),
                        )
                      : const Icon(Icons.person_add_alt_1),
                  label: const Text('Crear invitación'),
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}
