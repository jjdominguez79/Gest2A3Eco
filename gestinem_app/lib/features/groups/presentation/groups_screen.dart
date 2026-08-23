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
final groupsProvider = FutureProvider.autoDispose<List<MessagingGroup>>((
  ref,
) async {
  // El backend convierte aquí los antiguos equipos fijos en grupos editables.
  await ref.watch(internalThreadsProvider.future);
  return ref.watch(groupsRepositoryProvider).list();
});

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
                key: const Key('new-group-type'),
                initialValue: type,
                isExpanded: true,
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
    final name = TextEditingController(text: group.name);
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
                TextField(
                  key: const Key('group-name'),
                  controller: name,
                  decoration: const InputDecoration(
                    labelText: 'Nombre del grupo',
                  ),
                ),
                const SizedBox(height: 12),
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
              label: const Text('Guardar cambios'),
            ),
          ],
        ),
      ),
    );
    final updatedName = name.text.trim();
    name.dispose();
    if (save != true || updatedName.isEmpty || !context.mounted) return;
    try {
      final repository = ref.read(groupsRepositoryProvider);
      if (updatedName != group.name) {
        await repository.update(group, updatedName);
      }
      for (final id in selected.difference(original)) {
        await repository.addMember(group.id, 'staff', id);
      }
      for (final id in original.difference(selected)) {
        await repository.removeMember(group.id, id);
      }
      ref.invalidate(groupsProvider);
      ref.invalidate(internalThreadsProvider);
      if (context.mounted) {
        ScaffoldMessenger.of(
          context,
        ).showSnackBar(const SnackBar(content: Text('Grupo actualizado')));
      }
    } catch (error) {
      if (context.mounted) _showError(context, error);
    }
  }

  Future<void> _deleteGroup(
    BuildContext context,
    WidgetRef ref,
    MessagingGroup group,
  ) async {
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (dialogContext) => AlertDialog(
        title: const Text('Eliminar grupo'),
        content: Text(
          '¿Quieres eliminar “${group.name}”? Dejará de aparecer y sus miembros ya no podrán acceder al chat.',
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(dialogContext, false),
            child: const Text('Cancelar'),
          ),
          FilledButton(
            key: const Key('confirm-delete-group'),
            onPressed: () => Navigator.pop(dialogContext, true),
            style: FilledButton.styleFrom(
              backgroundColor: Theme.of(context).colorScheme.error,
            ),
            child: const Text('Eliminar'),
          ),
        ],
      ),
    );
    if (confirmed != true || !context.mounted) return;
    try {
      await ref.read(groupsRepositoryProvider).delete(group.id);
      ref.invalidate(groupsProvider);
      ref.invalidate(internalThreadsProvider);
      if (context.mounted) {
        ScaffoldMessenger.of(
          context,
        ).showSnackBar(const SnackBar(content: Text('Grupo eliminado')));
      }
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
    return Scaffold(
      appBar: AppBar(
        leading: IconButton(
          onPressed: () => context.go('/'),
          icon: const Icon(Icons.arrow_back),
        ),
        title: const Text('Gestionar grupos internos'),
        actions: [
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
              'GRUPOS INTERNOS',
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
                    trailing: profile.isAdmin
                        ? PopupMenuButton<String>(
                            key: Key('group-actions-${group.id}'),
                            tooltip: 'Acciones del grupo',
                            onSelected: (action) {
                              if (action == 'edit' &&
                                  group.type == 'staff_chat') {
                                _configureStaffGroup(context, ref, group);
                              } else if (action == 'delete') {
                                _deleteGroup(context, ref, group);
                              }
                            },
                            itemBuilder: (_) => [
                              if (group.type == 'staff_chat')
                                const PopupMenuItem(
                                  value: 'edit',
                                  child: ListTile(
                                    leading: Icon(
                                      Icons.manage_accounts_outlined,
                                    ),
                                    title: Text('Editar'),
                                  ),
                                ),
                              const PopupMenuItem(
                                value: 'delete',
                                child: ListTile(
                                  leading: Icon(Icons.delete_outline),
                                  title: Text('Eliminar'),
                                ),
                              ),
                            ],
                          )
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
