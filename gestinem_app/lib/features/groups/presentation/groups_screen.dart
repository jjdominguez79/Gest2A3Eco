import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../../core/api/api_client.dart';
import '../../../core/widgets/authenticated_avatar.dart';
import '../../auth/presentation/auth_controller.dart';
import '../../empleados/domain/empleado_despacho.dart';
import '../../empleados/presentation/empleados_screen.dart';
import '../../messaging/presentation/messaging_providers.dart';
import '../data/groups_repository.dart';
import '../domain/group.dart';

final groupsRepositoryProvider = Provider<GroupsRepository>(
  (ref) => GroupsRepository(ref.watch(apiClientProvider)),
);
final groupsProvider = FutureProvider.autoDispose<List<MessagingGroup>>(
  (ref) => ref.watch(groupsRepositoryProvider).list(),
);

class GroupsScreen extends ConsumerWidget {
  const GroupsScreen({super.key});

  String _baseUrl(WidgetRef ref) => ref
      .read(apiClientProvider)
      .dio
      .options
      .baseUrl
      .replaceAll(RegExp(r'/api/v1/messaging/?$'), '');

  Future<void> _create(BuildContext context, WidgetRef ref) async {
    final name = TextEditingController();
    var type = 'staff_chat';
    final accepted = await showDialog<bool>(
      context: context,
      builder: (context) => StatefulBuilder(
        builder: (context, setState) => AlertDialog(
          title: const Text('Nuevo grupo'),
          content: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              TextField(
                controller: name,
                decoration: const InputDecoration(labelText: 'Nombre'),
              ),
              const SizedBox(height: 12),
              DropdownButtonFormField<String>(
                initialValue: type,
                items: const [
                  DropdownMenuItem(
                    value: 'staff_chat',
                    child: Text('Chat interno de empleados'),
                  ),
                  DropdownMenuItem(
                    value: 'client_list',
                    child: Text('Lista de clientes para campañas'),
                  ),
                ],
                onChanged: (value) => setState(() => type = value!),
              ),
            ],
          ),
          actions: [
            TextButton(
              onPressed: () => Navigator.pop(context, false),
              child: const Text('Cancelar'),
            ),
            FilledButton(
              onPressed: () => Navigator.pop(context, true),
              child: const Text('Crear'),
            ),
          ],
        ),
      ),
    );
    if (accepted != true || name.text.trim().isEmpty || !context.mounted) {
      name.dispose();
      return;
    }
    try {
      final group = await ref
          .read(groupsRepositoryProvider)
          .create(name.text.trim(), type);
      ref.invalidate(groupsProvider);
      ref.invalidate(internalThreadsProvider);
      if (group.type == 'staff_chat' && context.mounted) {
        await _configureStaffGroup(context, ref, group);
      }
    } catch (error) {
      if (context.mounted) _showError(context, error);
    } finally {
      name.dispose();
    }
  }

  Future<void> _configureStaffGroup(
    BuildContext context,
    WidgetRef ref,
    MessagingGroup group,
  ) async {
    final employees = await ref.read(empleadosProvider.future);
    if (!context.mounted) return;
    final original = group.members
        .where((member) => member.memberType == 'staff')
        .map((member) => member.memberId)
        .toSet();
    final owners = group.members
        .where((member) => member.role == 'owner')
        .map((member) => member.memberId)
        .toSet();
    final selected = {...original};
    final save = await showDialog<bool>(
      context: context,
      builder: (dialogContext) => StatefulBuilder(
        builder: (dialogContext, setState) => AlertDialog(
          title: Text('Empleados de ${group.name}'),
          content: SizedBox(
            width: 520,
            height: 430,
            child: ListView(
              children: [
                const Text(
                  'Selecciona quién participará en este chat interno.',
                ),
                const SizedBox(height: 12),
                for (final employee in employees.where((item) => item.activo))
                  CheckboxListTile(
                    key: Key('group-employee-${employee.id}'),
                    value: selected.contains(employee.id),
                    onChanged: owners.contains(employee.id)
                        ? null
                        : (checked) => setState(() {
                            if (checked == true) {
                              selected.add(employee.id);
                            } else {
                              selected.remove(employee.id);
                            }
                          }),
                    secondary: _employeeAvatar(ref, employee),
                    title: Text(employee.nombreVisible),
                    subtitle: Text(
                      owners.contains(employee.id)
                          ? 'Administrador del grupo'
                          : employee.email,
                    ),
                  ),
              ],
            ),
          ),
          actions: [
            TextButton(
              onPressed: () => Navigator.pop(dialogContext, false),
              child: const Text('Cancelar'),
            ),
            FilledButton.icon(
              onPressed: () => Navigator.pop(dialogContext, true),
              icon: const Icon(Icons.save_outlined),
              label: const Text('Guardar miembros'),
            ),
          ],
        ),
      ),
    );
    if (save != true || !context.mounted) return;
    try {
      final repository = ref.read(groupsRepositoryProvider);
      for (final id in selected.difference(original)) {
        await repository.addMember(group.id, 'staff', id);
      }
      for (final id in original.difference(selected)) {
        await repository.removeMember(group.id, id);
      }
      ref.invalidate(groupsProvider);
      ref.invalidate(internalThreadsProvider);
      if (context.mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(content: Text('Miembros del grupo actualizados')),
        );
      }
    } catch (error) {
      if (context.mounted) _showError(context, error);
    }
  }

  Future<void> _chooseDirectEmployee(
    BuildContext context,
    WidgetRef ref,
  ) async {
    final profile = ref.read(sessionProvider).valueOrNull!.profile;
    final employees = (await ref.read(
      empleadosProvider.future,
    )).where((item) => item.activo && item.id != profile.id).toList();
    if (!context.mounted) return;
    final selected = await showDialog<EmpleadoDespacho>(
      context: context,
      builder: (dialogContext) => AlertDialog(
        title: const Text('Abrir chat con un empleado'),
        content: SizedBox(
          width: 500,
          height: 420,
          child: ListView(
            children: [
              for (final employee in employees)
                ListTile(
                  leading: _employeeAvatar(ref, employee),
                  title: Text(employee.nombreVisible),
                  subtitle: Text(employee.email),
                  onTap: () => Navigator.pop(dialogContext, employee),
                ),
            ],
          ),
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(dialogContext),
            child: const Text('Cancelar'),
          ),
        ],
      ),
    );
    if (selected == null || !context.mounted) return;
    try {
      final threadId = await ref
          .read(groupsRepositoryProvider)
          .createDirect(selected.id);
      ref.invalidate(internalThreadsProvider);
      if (context.mounted) context.go('/internal/$threadId');
    } catch (error) {
      if (context.mounted) _showError(context, error);
    }
  }

  AuthenticatedAvatar _employeeAvatar(
    WidgetRef ref,
    EmpleadoDespacho employee,
  ) => AuthenticatedAvatar(
    baseUrl: _baseUrl(ref),
    authToken: ref.read(sessionProvider).valueOrNull?.token ?? '',
    imagePath: employee.avatarConfigurado ? employee.avatarUrl : '',
    fallbackText: _initials(employee.nombreVisible),
    cacheVersion: employee.avatarConfigurado.toString(),
  );

  void _showError(BuildContext context, Object error) {
    ScaffoldMessenger.of(
      context,
    ).showSnackBar(SnackBar(content: Text(apiErrorMessage(error))));
  }

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final profile = ref.watch(sessionProvider).valueOrNull!.profile;
    final groups = ref.watch(groupsProvider);
    final threads = ref.watch(internalThreadsProvider);
    final token = ref.read(sessionProvider).valueOrNull?.token ?? '';
    return Scaffold(
      appBar: AppBar(
        leading: IconButton(
          onPressed: () => context.go('/'),
          icon: const Icon(Icons.arrow_back),
        ),
        title: const Text('Chats internos y grupos'),
        actions: [
          if (profile.isAdmin)
            IconButton(
              tooltip: 'Chat directo con un empleado',
              onPressed: () => _chooseDirectEmployee(context, ref),
              icon: const Icon(Icons.person_add_alt_1_outlined),
            ),
          if (profile.isAdmin)
            IconButton(
              tooltip: 'Crear grupo',
              onPressed: () => _create(context, ref),
              icon: const Icon(Icons.add),
            ),
        ],
      ),
      body: ListView(
        children: [
          const Padding(
            padding: EdgeInsets.fromLTRB(16, 16, 16, 8),
            child: Text(
              'CONVERSACIONES INTERNAS',
              style: TextStyle(fontWeight: FontWeight.bold),
            ),
          ),
          ...threads.when(
            data: (items) => items
                .map(
                  (thread) => ListTile(
                    leading: thread.kind == 'group'
                        ? const CircleAvatar(child: Icon(Icons.groups))
                        : AuthenticatedAvatar(
                            baseUrl: _baseUrl(ref),
                            authToken: token,
                            imagePath: thread.counterpartAvatarUrl,
                            fallbackText: _initials(thread.title),
                            cacheVersion: thread.id,
                          ),
                    title: Text(thread.title),
                    subtitle: Text(
                      thread.kind == 'group'
                          ? (thread.channel.isEmpty
                                ? 'Grupo dinámico'
                                : thread.channel)
                          : 'Chat directo',
                    ),
                    trailing: thread.unreadCount > 0
                        ? Badge(label: Text('${thread.unreadCount}'))
                        : null,
                    onTap: () => context.go('/internal/${thread.id}'),
                  ),
                )
                .toList(),
            loading: () => [const Center(child: CircularProgressIndicator())],
            error: (_, _) => [
              const ListTile(title: Text('No se pudieron cargar los chats')),
            ],
          ),
          const Divider(),
          const Padding(
            padding: EdgeInsets.fromLTRB(16, 10, 16, 8),
            child: Text(
              'GRUPOS DINÁMICOS',
              style: TextStyle(fontWeight: FontWeight.bold),
            ),
          ),
          ...groups.when(
            data: (items) => items
                .map(
                  (group) => ListTile(
                    leading: Icon(
                      group.type == 'staff_chat'
                          ? Icons.forum_outlined
                          : Icons.campaign_outlined,
                    ),
                    title: Text(group.name),
                    subtitle: Text(
                      '${group.type == 'staff_chat' ? 'Chat interno' : 'Lista para campañas'} · '
                      '${group.members.length} miembros',
                    ),
                    trailing: profile.isAdmin && group.type == 'staff_chat'
                        ? const Icon(Icons.manage_accounts_outlined)
                        : null,
                    onTap: profile.isAdmin && group.type == 'staff_chat'
                        ? () => _configureStaffGroup(context, ref, group)
                        : null,
                  ),
                )
                .toList(),
            loading: () => [const Center(child: CircularProgressIndicator())],
            error: (_, _) => [
              const ListTile(title: Text('No se pudieron cargar los grupos')),
            ],
          ),
        ],
      ),
    );
  }
}

String _initials(String value) {
  final words = value
      .trim()
      .split(RegExp(r'\s+'))
      .where((word) => word.isNotEmpty);
  final initials = words.take(2).map((word) => word[0]).join().toUpperCase();
  return initials.isEmpty ? '?' : initials;
}
