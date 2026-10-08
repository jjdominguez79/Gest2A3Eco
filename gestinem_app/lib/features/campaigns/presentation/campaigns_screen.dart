import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../../core/api/api_client.dart';
import '../../auth/presentation/auth_controller.dart';
import '../data/campaigns_repository.dart';
import '../domain/campaign.dart';
import '../../groups/domain/group.dart';
import '../../groups/presentation/groups_screen.dart';

final campaignsRepositoryProvider = Provider<CampaignsRepository>(
  (ref) => CampaignsRepository(ref.watch(apiClientProvider)),
);
final campaignsProvider = FutureProvider.autoDispose<List<Campaign>>(
  (ref) => ref.watch(campaignsRepositoryProvider).list(),
);

class CampaignsScreen extends ConsumerWidget {
  const CampaignsScreen({super.key});

  Future<void> _create(BuildContext context, WidgetRef ref) async {
    late final List<MessagingGroup> groups;
    late final List<CampaignClientTarget> clients;
    try {
      groups = (await ref.read(
        groupsProvider.future,
      )).where((group) => group.type == 'client_list').toList();
      clients = await ref.read(campaignsRepositoryProvider).clients();
    } catch (error) {
      if (context.mounted) {
        ScaffoldMessenger.of(
          context,
        ).showSnackBar(SnackBar(content: Text(apiErrorMessage(error))));
      }
      return;
    }
    if (!context.mounted) return;
    final name = TextEditingController();
    final body = TextEditingController();
    var allClients = false;
    final groupIds = <String>{};
    final clientIds = <String>{};
    final accepted = await showDialog<bool>(
      context: context,
      builder: (context) => StatefulBuilder(
        builder: (context, setState) => AlertDialog(
          title: const Text('Nueva difusión'),
          content: SizedBox(
            width: 520,
            child: SingleChildScrollView(
              child: Column(
                mainAxisSize: MainAxisSize.min,
                children: [
                  TextField(
                    key: const Key('broadcast-name'),
                    controller: name,
                    onChanged: (_) => setState(() {}),
                    decoration: const InputDecoration(labelText: 'Nombre'),
                  ),
                  const SizedBox(height: 12),
                  TextField(
                    key: const Key('broadcast-body'),
                    controller: body,
                    onChanged: (_) => setState(() {}),
                    minLines: 4,
                    maxLines: 8,
                    decoration: const InputDecoration(labelText: 'Mensaje'),
                  ),
                  const SizedBox(height: 12),
                  const ListTile(
                    contentPadding: EdgeInsets.zero,
                    leading: CircleAvatar(child: Text('CG')),
                    title: Text('Canal general'),
                    subtitle: Text(
                      'Cada cliente recibirá el mensaje en su conversación.',
                    ),
                  ),
                  CheckboxListTile(
                    key: const Key('broadcast-all-clients'),
                    value: allClients,
                    title: const Text('Todos los clientes'),
                    onChanged: (value) =>
                        setState(() => allClients = value ?? false),
                  ),
                  if (!allClients) ...[
                    if (groups.isNotEmpty)
                      const Align(
                        alignment: Alignment.centerLeft,
                        child: Text(
                          'Listas',
                          style: TextStyle(fontWeight: FontWeight.bold),
                        ),
                      ),
                    for (final group in groups)
                      CheckboxListTile(
                        value: groupIds.contains(group.id),
                        title: Text(group.name),
                        subtitle: Text(
                          '${group.members.length} ${group.members.length == 1 ? 'cliente' : 'clientes'}',
                        ),
                        dense: true,
                        onChanged: (selected) => setState(
                          () => selected == true
                              ? groupIds.add(group.id)
                              : groupIds.remove(group.id),
                        ),
                      ),
                    const Align(
                      alignment: Alignment.centerLeft,
                      child: Text(
                        'Clientes individuales',
                        style: TextStyle(fontWeight: FontWeight.bold),
                      ),
                    ),
                    for (final client in clients)
                      CheckboxListTile(
                        value: clientIds.contains(client.id),
                        title: Text(client.displayName),
                        subtitle: Text(
                          [
                            client.companyCode,
                            client.company,
                            client.email,
                          ].where((value) => value.isNotEmpty).join(' · '),
                        ),
                        dense: true,
                        onChanged: (selected) => setState(
                          () => selected == true
                              ? clientIds.add(client.id)
                              : clientIds.remove(client.id),
                        ),
                      ),
                  ],
                ],
              ),
            ),
          ),
          actions: [
            TextButton(
              onPressed: () => Navigator.pop(context, false),
              child: const Text('Cancelar'),
            ),
            FilledButton(
              key: const Key('broadcast-send'),
              onPressed:
                  name.text.trim().isNotEmpty &&
                      body.text.trim().isNotEmpty &&
                      (allClients ||
                          groupIds.isNotEmpty ||
                          clientIds.isNotEmpty)
                  ? () => Navigator.pop(context, true)
                  : null,
              child: const Text('Enviar'),
            ),
          ],
        ),
      ),
    );
    if (accepted == true) {
      try {
        await ref
            .read(campaignsRepositoryProvider)
            .create(
              name: name.text.trim(),
              body: body.text.trim(),
              channel: 'general',
              allClients: allClients,
              groupIds: groupIds.toList(),
              clientIds: clientIds.toList(),
            );
        ref.invalidate(campaignsProvider);
        if (context.mounted) {
          ScaffoldMessenger.of(
            context,
          ).showSnackBar(const SnackBar(content: Text('Difusión enviada')));
        }
      } catch (error) {
        if (context.mounted) {
          ScaffoldMessenger.of(
            context,
          ).showSnackBar(SnackBar(content: Text(apiErrorMessage(error))));
        }
      }
    }
    name.dispose();
    body.dispose();
  }

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final profile = ref.watch(sessionProvider).valueOrNull?.profile;
    if (profile?.isAdmin != true) {
      return const Scaffold(
        body: Center(
          child: Text('Solo los administradores pueden enviar difusiones.'),
        ),
      );
    }
    final campaigns = ref.watch(campaignsProvider);
    return Scaffold(
      appBar: AppBar(
        leading: IconButton(
          onPressed: () => context.go('/'),
          icon: const Icon(Icons.arrow_back),
        ),
        title: const Text('Difusiones'),
        actions: [
          IconButton(
            onPressed: () => _create(context, ref),
            tooltip: 'Nueva difusión',
            icon: const Icon(Icons.add),
          ),
        ],
      ),
      body: campaigns.when(
        loading: () => const Center(child: CircularProgressIndicator()),
        error: (error, _) =>
            Center(child: Text('No se pudieron cargar las difusiones: $error')),
        data: (items) => items.isEmpty
            ? const Center(child: Text('Todavía no hay difusiones'))
            : ListView.separated(
                itemCount: items.length,
                separatorBuilder: (_, _) => const Divider(height: 1),
                itemBuilder: (context, index) {
                  final campaign = items[index];
                  return ListTile(
                    leading: const CircleAvatar(child: Icon(Icons.campaign)),
                    title: Text(campaign.name),
                    subtitle: Text('${campaign.recipientCount} destinatarios'),
                    trailing: Chip(label: Text(campaign.status)),
                    onLongPress:
                        campaign.status == 'failed' ||
                            campaign.status == 'partial'
                        ? () async {
                            await ref
                                .read(campaignsRepositoryProvider)
                                .retry(campaign.id);
                            ref.invalidate(campaignsProvider);
                          }
                        : null,
                  );
                },
              ),
      ),
    );
  }
}
