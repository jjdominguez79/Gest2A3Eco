import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../../core/api/api_client.dart';
import '../domain/client_organization.dart';
import 'clients_screen.dart';
import 'messaging_providers.dart';

class ClientDetailScreen extends ConsumerStatefulWidget {
  const ClientDetailScreen({super.key, required this.companyCode});

  final String companyCode;

  @override
  ConsumerState<ClientDetailScreen> createState() => _ClientDetailScreenState();
}

class _ClientDetailScreenState extends ConsumerState<ClientDetailScreen> {
  bool _working = false;

  Future<void> _setAccess(ClientOrganization client, bool active) async {
    final destructive = !active;
    if (destructive) {
      final pending = client.accessStatus == 'pending';
      final confirmed = await showDialog<bool>(
        context: context,
        builder: (dialogContext) => AlertDialog(
          title: Text(pending ? 'Retirar invitación' : 'Desactivar acceso'),
          content: Text(
            pending
                ? 'La invitación de ${client.displayName} dejará de ser válida.'
                : '${client.displayName} dejará de poder iniciar sesión. El historial de mensajes se conservará.',
          ),
          actions: [
            TextButton(
              onPressed: () => Navigator.pop(dialogContext, false),
              child: const Text('Cancelar'),
            ),
            FilledButton(
              onPressed: () => Navigator.pop(dialogContext, true),
              child: Text(pending ? 'Retirar' : 'Desactivar'),
            ),
          ],
        ),
      );
      if (confirmed != true) return;
    }
    await _run(() async {
      await ref
          .read(messagingRepositoryProvider)
          .setClientAccess(client.companyCode, active);
      ref.invalidate(clientOrganizationsProvider);
      ref.invalidate(conversationTargetsProvider);
      ref.invalidate(conversationsProvider);
    });
  }

  Future<void> _openDirect(ClientOrganization client) => _run(() async {
    final conversation = await ref
        .read(messagingRepositoryProvider)
        .startDirectConversation(client.companyCode);
    ref.invalidate(clientOrganizationsProvider);
    ref.invalidate(conversationTargetsProvider);
    ref.invalidate(conversationsProvider);
    if (mounted) context.go('/conversation/${conversation.id}');
  });

  Future<void> _run(Future<void> Function() operation) async {
    if (_working) return;
    setState(() => _working = true);
    try {
      await operation();
    } catch (error) {
      if (mounted) {
        ScaffoldMessenger.of(
          context,
        ).showSnackBar(SnackBar(content: Text(apiErrorMessage(error))));
      }
    } finally {
      if (mounted) setState(() => _working = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final organizations = ref.watch(clientOrganizationsProvider);
    return Scaffold(
      appBar: AppBar(
        leading: IconButton(
          onPressed: () => context.go('/clients'),
          icon: const Icon(Icons.arrow_back),
        ),
        title: const Text('Ficha del cliente'),
      ),
      body: organizations.when(
        loading: () => const Center(child: CircularProgressIndicator()),
        error: (error, _) =>
            Center(child: Text('No se pudo cargar el cliente: $error')),
        data: (rows) {
          final matches = rows.where(
            (row) => row.companyCode == widget.companyCode,
          );
          if (matches.isEmpty) {
            return const Center(child: Text('Cliente no encontrado'));
          }
          final client = matches.first;
          return ListView(
            padding: const EdgeInsets.all(20),
            children: [
              Card(
                child: Padding(
                  padding: const EdgeInsets.all(20),
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(
                        client.displayName,
                        style: Theme.of(context).textTheme.headlineSmall,
                      ),
                      const SizedBox(height: 6),
                      Text(client.companyCode),
                      const SizedBox(height: 14),
                      ClientStatusBadge(status: client.accessStatus),
                    ],
                  ),
                ),
              ),
              const SizedBox(height: 12),
              Card(
                child: Column(
                  children: [
                    const ListTile(
                      leading: Icon(Icons.info_outline),
                      title: Text('Acceso a Gestinem'),
                    ),
                    if (client.contactName.isNotEmpty)
                      ListTile(
                        leading: const Icon(Icons.person_outline),
                        title: Text(client.contactName),
                        subtitle: const Text('Persona de contacto'),
                      ),
                    if (client.contactEmail.isNotEmpty)
                      ListTile(
                        leading: const Icon(Icons.email_outlined),
                        title: Text(client.contactEmail),
                        subtitle: const Text('Correo de acceso'),
                      ),
                    if (client.accessStatus == 'pending' &&
                        client.invitationExpiresAt != null)
                      ListTile(
                        leading: const Icon(Icons.schedule),
                        title: Text(_formatDate(client.invitationExpiresAt!)),
                        subtitle: const Text('La invitación caduca'),
                      ),
                  ],
                ),
              ),
              const SizedBox(height: 20),
              if ({'active', 'pending'}.contains(client.accessStatus))
                FilledButton.icon(
                  key: const Key('client-open-direct'),
                  onPressed: _working ? null : () => _openDirect(client),
                  icon: const Icon(Icons.chat_outlined),
                  label: const Text('Abrir chat directo'),
                ),
              if (client.accessStatus == 'not_invited' ||
                  client.accessStatus == 'invitation_expired' ||
                  (client.accessStatus == 'disabled' &&
                      !client.hasAcceptedAccess))
                FilledButton.icon(
                  key: const Key('client-invite'),
                  onPressed: _working
                      ? null
                      : () => context.go(
                          '/invite-client?company=${client.companyCode}',
                        ),
                  icon: const Icon(Icons.person_add_alt_1),
                  label: Text(
                    client.accessStatus == 'not_invited'
                        ? 'Invitar cliente'
                        : 'Volver a invitar',
                  ),
                ),
              if (client.accessStatus == 'pending') ...[
                const SizedBox(height: 10),
                OutlinedButton.icon(
                  key: const Key('client-withdraw-invite'),
                  onPressed: _working ? null : () => _setAccess(client, false),
                  icon: const Icon(Icons.cancel_outlined),
                  label: const Text('Retirar invitación'),
                ),
              ],
              if (client.accessStatus == 'active') ...[
                const SizedBox(height: 10),
                OutlinedButton.icon(
                  key: const Key('client-disable-access'),
                  onPressed: _working ? null : () => _setAccess(client, false),
                  icon: const Icon(Icons.person_off_outlined),
                  label: const Text('Desactivar acceso'),
                ),
              ],
              if (client.accessStatus == 'disabled' && client.hasAcceptedAccess)
                FilledButton.icon(
                  key: const Key('client-enable-access'),
                  onPressed: _working ? null : () => _setAccess(client, true),
                  icon: const Icon(Icons.person_add_outlined),
                  label: const Text('Reactivar acceso'),
                ),
              if (_working) ...[
                const SizedBox(height: 16),
                const Center(child: CircularProgressIndicator()),
              ],
            ],
          );
        },
      ),
    );
  }
}

String _formatDate(DateTime value) =>
    '${value.day.toString().padLeft(2, '0')}/${value.month.toString().padLeft(2, '0')}/${value.year} '
    '${value.hour.toString().padLeft(2, '0')}:${value.minute.toString().padLeft(2, '0')}';
