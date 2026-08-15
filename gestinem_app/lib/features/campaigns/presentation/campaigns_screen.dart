import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../auth/presentation/auth_controller.dart';
import '../data/campaigns_repository.dart';
import '../domain/campaign.dart';

final campaignsRepositoryProvider = Provider<CampaignsRepository>((ref) => CampaignsRepository(ref.watch(apiClientProvider)));
final campaignsProvider = FutureProvider.autoDispose<List<Campaign>>((ref) => ref.watch(campaignsRepositoryProvider).list());

class CampaignsScreen extends ConsumerWidget {
  const CampaignsScreen({super.key});

  Future<void> _create(BuildContext context, WidgetRef ref) async {
    final name = TextEditingController();
    final body = TextEditingController();
    var channel = 'fiscal';
    final accepted = await showDialog<bool>(context: context, builder: (context) => StatefulBuilder(builder: (context, setState) => AlertDialog(
      title: const Text('Nueva campana'),
      content: SizedBox(width: 480, child: Column(mainAxisSize: MainAxisSize.min, children: [
        TextField(controller: name, decoration: const InputDecoration(labelText: 'Nombre')),
        const SizedBox(height: 12),
        TextField(controller: body, minLines: 4, maxLines: 8, decoration: const InputDecoration(labelText: 'Mensaje')),
        const SizedBox(height: 12),
        DropdownButtonFormField<String>(initialValue: channel, items: const [DropdownMenuItem(value: 'fiscal', child: Text('Contable / Fiscal')), DropdownMenuItem(value: 'laboral', child: Text('Laboral'))], onChanged: (value) => setState(() => channel = value!)),
        const SizedBox(height: 10),
        const Text('Esta primera interfaz envia a todos los clientes. Las listas y la seleccion manual ya estan disponibles en la API.'),
      ])),
      actions: [TextButton(onPressed: () => Navigator.pop(context, false), child: const Text('Cancelar')), FilledButton(onPressed: () => Navigator.pop(context, true), child: const Text('Enviar'))],
    )));
    if (accepted == true && name.text.trim().isNotEmpty && body.text.trim().isNotEmpty) {
      await ref.read(campaignsRepositoryProvider).create(name: name.text.trim(), body: body.text.trim(), channel: channel, allClients: true);
      ref.invalidate(campaignsProvider);
    }
  }

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final campaigns = ref.watch(campaignsProvider);
    return Scaffold(
      appBar: AppBar(leading: IconButton(onPressed: () => context.go('/'), icon: const Icon(Icons.arrow_back)), title: const Text('Campanas'), actions: [IconButton(onPressed: () => _create(context, ref), icon: const Icon(Icons.add))]),
      body: campaigns.when(
        loading: () => const Center(child: CircularProgressIndicator()),
        error: (error, _) => Center(child: Text('No se pudieron cargar las campanas: $error')),
        data: (items) => items.isEmpty ? const Center(child: Text('Todavia no hay campanas')) : ListView.separated(
          itemCount: items.length,
          separatorBuilder: (_, _) => const Divider(height: 1),
          itemBuilder: (context, index) {
            final campaign = items[index];
            return ListTile(
              leading: const CircleAvatar(child: Icon(Icons.campaign)),
              title: Text(campaign.name),
              subtitle: Text('${campaign.recipientCount} destinatarios'),
              trailing: Chip(label: Text(campaign.status)),
              onLongPress: campaign.status == 'failed' || campaign.status == 'partial' ? () async { await ref.read(campaignsRepositoryProvider).retry(campaign.id); ref.invalidate(campaignsProvider); } : null,
            );
          },
        ),
      ),
    );
  }
}
