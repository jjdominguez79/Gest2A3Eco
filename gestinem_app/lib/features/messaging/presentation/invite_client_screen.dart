import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../../core/api/api_client.dart';
import '../../../core/validation/email_validation.dart';
import '../../auth/presentation/auth_controller.dart';
import '../domain/conversation.dart';
import 'messaging_providers.dart';

class InviteClientScreen extends ConsumerStatefulWidget {
  const InviteClientScreen({super.key, this.companyCode = ''});

  final String companyCode;

  @override
  ConsumerState<InviteClientScreen> createState() => _InviteClientScreenState();
}

class _InviteClientScreenState extends ConsumerState<InviteClientScreen> {
  final _formKey = GlobalKey<FormState>();
  final _name = TextEditingController();
  final _email = TextEditingController();
  String _companyText = '';
  Organization? _selectedOrg;
  bool _sendEmail = true;
  bool _sending = false;

  @override
  void initState() {
    super.initState();
    _companyText = widget.companyCode;
  }

  @override
  void dispose() {
    _name.dispose();
    _email.dispose();
    super.dispose();
  }

  String get _companyCode {
    final selected = _selectedOrg;
    if (selected != null) return selected.companyCode;
    return _companyText.trim().split(RegExp(r'\s+|·')).first.toUpperCase();
  }

  bool get _isResend => _selectedOrg?.hasExistingInvitation ?? false;

  Future<void> _submit() async {
    if (!_formKey.currentState!.validate() || _sending) return;
    setState(() => _sending = true);
    try {
      final result = await ref
          .read(messagingRepositoryProvider)
          .inviteClient(
            companyCode: _companyCode,
            name: _name.text.trim(),
            email: normalizeEmail(_email.text),
            sendEmail: _sendEmail,
          );
      ref.invalidate(conversationsProvider);
      ref.invalidate(organizationsProvider);
      ref.invalidate(conversationTargetsProvider);
      ref.invalidate(clientOrganizationsProvider);
      if (!mounted) return;
      await _showResult(result);
      if (mounted) context.go('/clients/$_companyCode');
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
        title: Text(
          queued
              ? (_isResend ? 'Invitación reenviada' : 'Invitación enviada')
              : (_isResend ? 'Invitación regenerada' : 'Invitación creada'),
        ),
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
    final orgsAsync = ref.watch(organizationsProvider);
    return Scaffold(
      appBar: AppBar(
        leading: IconButton(
          onPressed: () => context.go('/clients'),
          icon: const Icon(Icons.arrow_back),
        ),
        title: const Text('Invitar cliente'),
      ),
      body: orgsAsync.when(
        loading: () => const Center(child: CircularProgressIndicator()),
        error: (e, _) => Center(child: Text('Error: ${apiErrorMessage(e)}')),
        data: (allOrgs) {
          // Solo mostrar organizaciones que se pueden invitar (no activas ni deshabilitadas)
          final invitableOrgs =
              allOrgs
                  .where(
                    (o) =>
                        o.canInvite ||
                        (widget.companyCode.isNotEmpty &&
                            o.companyCode == widget.companyCode),
                  )
                  .toList()
                ..sort((a, b) => a.displayName.compareTo(b.displayName));

          return Center(
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
                    Autocomplete<Organization>(
                      initialValue: TextEditingValue(text: widget.companyCode),
                      displayStringForOption: (org) =>
                          '${org.companyCode} · ${org.displayName}',
                      optionsBuilder: (value) {
                        _companyText = value.text;
                        final query = value.text.trim().toLowerCase();
                        if (query.isEmpty) return invitableOrgs.take(12);
                        return invitableOrgs.where(
                          (org) =>
                              org.companyCode.toLowerCase().contains(query) ||
                              org.displayName.toLowerCase().contains(query),
                        );
                      },
                      optionsViewBuilder: (context, onSelected, options) =>
                          _OptionsView(
                            options: options.toList(),
                            onSelected: onSelected,
                          ),
                      onSelected: (org) {
                        setState(() => _selectedOrg = org);
                        _companyText = org.companyCode;
                        if (_email.text.trim().isEmpty &&
                            isValidEmail(org.email)) {
                          _email.text = normalizeEmail(org.email);
                        }
                      },
                      fieldViewBuilder:
                          (context, controller, focusNode, onSubmit) =>
                              TextFormField(
                                key: const Key('invite-company'),
                                controller: controller,
                                focusNode: focusNode,
                                onChanged: (value) {
                                  _companyText = value;
                                  setState(() => _selectedOrg = null);
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
                    // Chip de estado si la organización ya tiene una invitación previa
                    if (_selectedOrg?.hasExistingInvitation ?? false) ...[
                      const SizedBox(height: 8),
                      _StatusChip(status: _selectedOrg!.clientAccessStatus),
                    ],
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
                        return isValidEmail(value ?? '')
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
                          : Icon(
                              _isResend
                                  ? Icons.refresh
                                  : Icons.person_add_alt_1,
                            ),
                      label: Text(
                        _isResend ? 'Reenviar invitación' : 'Crear invitación',
                      ),
                    ),
                  ],
                ),
              ),
            ),
          );
        },
      ),
    );
  }
}

/// Vista personalizada del desplegable con chip de estado.
class _OptionsView extends StatelessWidget {
  const _OptionsView({required this.options, required this.onSelected});

  final List<Organization> options;
  final AutocompleteOnSelected<Organization> onSelected;

  @override
  Widget build(BuildContext context) {
    return Align(
      alignment: Alignment.topLeft,
      child: Material(
        elevation: 4,
        borderRadius: BorderRadius.circular(8),
        child: ConstrainedBox(
          constraints: const BoxConstraints(maxHeight: 300),
          child: ListView.builder(
            padding: EdgeInsets.zero,
            shrinkWrap: true,
            itemCount: options.length,
            itemBuilder: (context, index) {
              final org = options[index];
              return InkWell(
                onTap: () => onSelected(org),
                child: Padding(
                  padding: const EdgeInsets.symmetric(
                    horizontal: 16,
                    vertical: 10,
                  ),
                  child: Row(
                    children: [
                      Expanded(
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            Text(
                              '${org.companyCode} · ${org.displayName}',
                              overflow: TextOverflow.ellipsis,
                            ),
                            if (org.email.trim().isNotEmpty)
                              Text(
                                normalizeEmail(org.email),
                                overflow: TextOverflow.ellipsis,
                                style: Theme.of(context).textTheme.bodySmall,
                              ),
                          ],
                        ),
                      ),
                      if (org.hasExistingInvitation) ...[
                        const SizedBox(width: 8),
                        _StatusChip(
                          status: org.clientAccessStatus,
                          small: true,
                        ),
                      ],
                    ],
                  ),
                ),
              );
            },
          ),
        ),
      ),
    );
  }
}

/// Chip visual que indica el estado de la invitación.
class _StatusChip extends StatelessWidget {
  const _StatusChip({required this.status, this.small = false});

  final String status;
  final bool small;

  @override
  Widget build(BuildContext context) {
    final (label, color) = switch (status) {
      'pending' => ('Invitación pendiente', Colors.amber.shade700),
      'invitation_expired' => ('Invitación caducada', Colors.orange.shade700),
      _ => ('', Colors.grey),
    };
    if (label.isEmpty) return const SizedBox.shrink();
    return Chip(
      label: Text(
        label,
        style: TextStyle(fontSize: small ? 11 : 12, color: Colors.white),
      ),
      backgroundColor: color,
      padding: small
          ? const EdgeInsets.symmetric(horizontal: 4, vertical: 0)
          : null,
      materialTapTargetSize: MaterialTapTargetSize.shrinkWrap,
      visualDensity: VisualDensity.compact,
    );
  }
}
