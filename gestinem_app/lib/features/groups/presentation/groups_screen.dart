import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../auth/presentation/auth_controller.dart';
import '../../messaging/presentation/messaging_providers.dart';
import '../data/groups_repository.dart';
import '../domain/group.dart';

final groupsRepositoryProvider = Provider<GroupsRepository>((ref) => GroupsRepository(ref.watch(apiClientProvider)));
final groupsProvider = FutureProvider.autoDispose<List<MessagingGroup>>((ref) => ref.watch(groupsRepositoryProvider).list());

class GroupsScreen extends ConsumerWidget {
  const GroupsScreen({super.key});

  Future<void> _create(BuildContext context, WidgetRef ref) async {
    final name = TextEditingController();
    var type = 'staff_chat';
    final accepted = await showDialog<bool>(context: context, builder: (context) => StatefulBuilder(builder: (context, setState) => AlertDialog(
      title: const Text('Nuevo grupo'),
      content: Column(mainAxisSize: MainAxisSize.min, children: [
        TextField(controller: name, decoration: const InputDecoration(labelText: 'Nombre')),
        const SizedBox(height: 12),
        DropdownButtonFormField<String>(initialValue: type, items: const [
          DropdownMenuItem(value: 'staff_chat', child: Text('Chat interno')),
          DropdownMenuItem(value: 'client_list', child: Text('Lista de clientes')),
        ], onChanged: (value) => setState(() => type = value!)),
      ]),
      actions: [TextButton(onPressed: () => Navigator.pop(context, false), child: const Text('Cancelar')), FilledButton(onPressed: () => Navigator.pop(context, true), child: const Text('Crear'))],
    )));
    if (accepted == true && name.text.trim().isNotEmpty) {
      await ref.read(groupsRepositoryProvider).create(name.text.trim(), type);
      ref.invalidate(groupsProvider);
      ref.invalidate(internalThreadsProvider);
    }
  }

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final profile = ref.watch(sessionProvider).valueOrNull!.profile;
    final groups = ref.watch(groupsProvider);
    final threads = ref.watch(internalThreadsProvider);
    return Scaffold(
      appBar: AppBar(
        leading: IconButton(onPressed: () => context.go('/'), icon: const Icon(Icons.arrow_back)),
        title: const Text('Chats internos y grupos'),
        actions: [if (profile.isAdmin) IconButton(onPressed: () => _create(context, ref), icon: const Icon(Icons.add))],
      ),
      body: ListView(children: [
        const Padding(padding: EdgeInsets.fromLTRB(16, 16, 16, 8), child: Text('CONVERSACIONES INTERNAS', style: TextStyle(fontWeight: FontWeight.bold))),
        ...threads.when(data: (items) => items.map((thread) => ListTile(
          leading: Icon(thread.kind == 'group' ? Icons.groups : Icons.person_outline),
          title: Text(thread.title),
          subtitle: Text(thread.channel),
          trailing: thread.unreadCount > 0 ? Badge(label: Text('${thread.unreadCount}')) : null,
          onTap: () => context.go('/internal/${thread.id}'),
        )).toList(), loading: () => [const Center(child: CircularProgressIndicator())], error: (_, _) => [const ListTile(title: Text('No se pudieron cargar los chats'))]),
        const Divider(),
        const Padding(padding: EdgeInsets.fromLTRB(16, 10, 16, 8), child: Text('GRUPOS DINAMICOS', style: TextStyle(fontWeight: FontWeight.bold))),
        ...groups.when(data: (items) => items.map((group) => ListTile(
          leading: Icon(group.type == 'staff_chat' ? Icons.forum_outlined : Icons.campaign_outlined),
          title: Text(group.name),
          subtitle: Text('${group.type == 'staff_chat' ? 'Chat interno' : 'Lista de clientes'} · ${group.members.length} miembros'),
        )).toList(), loading: () => [const Center(child: CircularProgressIndicator())], error: (_, _) => [const ListTile(title: Text('No se pudieron cargar los grupos'))]),
      ]),
    );
  }
}
