import 'package:file_picker/file_picker.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../../core/api/api_client.dart';
import '../../../core/widgets/authenticated_avatar.dart';
import '../../auth/presentation/auth_controller.dart';
import '../../campaigns/data/campaigns_repository.dart';
import '../../campaigns/domain/campaign.dart';
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
final clientListTargetsProvider =
    FutureProvider.autoDispose<List<CampaignClientTarget>>(
      (ref) => CampaignsRepository(ref.watch(apiClientProvider)).clients(),
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
          title: const Text('Nuevo grupo o lista'),
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
                    child: Text('Lista de clientes para difusión'),
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
      } else if (context.mounted) {
        await _configureClientList(context, ref, group);
      }
    } catch (error) {
      if (context.mounted) _showError(context, error);
    } finally {
      name.dispose();
    }
  }

  Future<void> _configureClientList(
    BuildContext context,
    WidgetRef ref,
    MessagingGroup group,
  ) async {
    late final List<CampaignClientTarget> clients;
    try {
      clients = await ref.read(clientListTargetsProvider.future);
    } catch (error) {
      if (context.mounted) _showError(context, error);
      return;
    }
    if (!context.mounted) return;
    final name = TextEditingController(text: group.name);
    final search = TextEditingController();
    final selected = group.members
        .where((member) => member.memberType == 'client')
        .map((member) => member.memberId)
        .toSet();
    final save = await showDialog<bool>(
      context: context,
      builder: (dialogContext) => StatefulBuilder(
        builder: (dialogContext, setState) {
          final query = search.text.trim().toLowerCase();
          final visible = clients
              .where((client) {
                if (query.isEmpty) return true;
                return client.name.toLowerCase().contains(query) ||
                    client.company.toLowerCase().contains(query) ||
                    client.companyCode.toLowerCase().contains(query) ||
                    client.email.toLowerCase().contains(query);
              })
              .toList(growable: false);
          return AlertDialog(
            title: Text('Clientes de ${group.name}'),
            content: SizedBox(
              width: 560,
              height: 500,
              child: Column(
                children: [
                  TextField(
                    key: const Key('client-list-name'),
                    controller: name,
                    decoration: const InputDecoration(
                      labelText: 'Nombre de la lista',
                    ),
                  ),
                  const SizedBox(height: 12),
                  TextField(
                    key: const Key('client-list-search'),
                    controller: search,
                    onChanged: (_) => setState(() {}),
                    decoration: const InputDecoration(
                      prefixIcon: Icon(Icons.search),
                      labelText: 'Buscar clientes',
                    ),
                  ),
                  const SizedBox(height: 8),
                  Row(
                    children: [
                      Text('${selected.length} seleccionados'),
                      const Spacer(),
                      TextButton(
                        onPressed: visible.isEmpty
                            ? null
                            : () => setState(
                                () => selected.addAll(
                                  visible.map((client) => client.id),
                                ),
                              ),
                        child: const Text('Seleccionar visibles'),
                      ),
                    ],
                  ),
                  const Divider(height: 1),
                  Expanded(
                    child: visible.isEmpty
                        ? const Center(
                            child: Text('No hay clientes con este filtro'),
                          )
                        : ListView.builder(
                            itemCount: visible.length,
                            itemBuilder: (context, index) {
                              final client = visible[index];
                              return CheckboxListTile(
                                key: Key('client-list-member-${client.id}'),
                                value: selected.contains(client.id),
                                title: Text(client.displayName),
                                subtitle: Text(
                                  [
                                        client.companyCode,
                                        if (client.company.isNotEmpty)
                                          client.company,
                                        client.email,
                                      ]
                                      .where((value) => value.isNotEmpty)
                                      .join(' · '),
                                ),
                                onChanged: (checked) => setState(() {
                                  if (checked == true) {
                                    selected.add(client.id);
                                  } else {
                                    selected.remove(client.id);
                                  }
                                }),
                              );
                            },
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
                key: const Key('save-client-list'),
                onPressed: () => Navigator.pop(dialogContext, true),
                icon: const Icon(Icons.save_outlined),
                label: const Text('Guardar lista'),
              ),
            ],
          );
        },
      ),
    );
    final updatedName = name.text.trim();
    name.dispose();
    search.dispose();
    if (save != true || updatedName.isEmpty || !context.mounted) return;
    try {
      final repository = ref.read(groupsRepositoryProvider);
      if (updatedName != group.name) {
        await repository.update(group, updatedName);
      }
      await repository.replaceClientMembers(group.id, selected);
      ref.invalidate(groupsProvider);
      if (context.mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(content: Text('Lista de clientes actualizada')),
        );
      }
    } catch (error) {
      if (context.mounted) _showError(context, error);
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
        title: Text(
          group.type == 'staff_chat'
              ? 'Pasar grupo a histórico'
              : 'Eliminar grupo',
        ),
        content: Text(
          group.type == 'staff_chat'
              ? '“${group.name}” quedará en modo solo lectura. Sus mensajes y miembros se conservarán para consulta de administradores.'
              : '¿Quieres eliminar “${group.name}”?',
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
            child: Text(
              group.type == 'staff_chat' ? 'Pasar a histórico' : 'Eliminar',
            ),
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
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(
            content: Text(
              group.type == 'staff_chat'
                  ? 'Grupo guardado como histórico'
                  : 'Grupo eliminado',
            ),
          ),
        );
      }
    } catch (error) {
      if (context.mounted) _showError(context, error);
    }
  }

  Future<void> _changeGroupAvatar(
    BuildContext context,
    WidgetRef ref,
    MessagingGroup group,
  ) async {
    try {
      final files = await FilePicker.pickFiles(
        type: FileType.custom,
        allowedExtensions: ['jpg', 'jpeg', 'png', 'webp'],
      );
      if (files.isEmpty) return;
      await ref
          .read(groupsRepositoryProvider)
          .updateAvatar(group.id, files.first);
      ref.invalidate(groupsProvider);
      ref.invalidate(internalThreadsProvider);
      if (context.mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(content: Text('Avatar del grupo actualizado')),
        );
      }
    } catch (error) {
      if (context.mounted) _showError(context, error);
    }
  }

  Future<void> _deleteGroupAvatar(
    BuildContext context,
    WidgetRef ref,
    MessagingGroup group,
  ) async {
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (dialogContext) => AlertDialog(
        title: const Text('Eliminar avatar'),
        content: Text('¿Quieres eliminar el avatar de “${group.name}”?'),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(dialogContext, false),
            child: const Text('Cancelar'),
          ),
          FilledButton(
            key: const Key('confirm-delete-group-avatar'),
            onPressed: () => Navigator.pop(dialogContext, true),
            child: const Text('Eliminar'),
          ),
        ],
      ),
    );
    if (confirmed != true || !context.mounted) return;
    try {
      await ref.read(groupsRepositoryProvider).deleteAvatar(group.id);
      ref.invalidate(groupsProvider);
      ref.invalidate(internalThreadsProvider);
      if (context.mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(content: Text('Avatar del grupo eliminado')),
        );
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

  Widget _groupTile(
    BuildContext context,
    WidgetRef ref,
    MessagingGroup group,
    bool isAdmin,
  ) {
    final isClientList = group.type == 'client_list';
    return ListTile(
      key: Key('group-${group.id}'),
      leading: isClientList
          ? const CircleAvatar(child: Icon(Icons.format_list_bulleted))
          : AuthenticatedAvatar(
              baseUrl: _baseUrl(ref),
              authToken: ref.read(sessionProvider).valueOrNull?.token ?? '',
              imagePath: group.avatarUrl,
              fallbackText: _initials(group.name),
              cacheVersion: group.avatarVersion,
            ),
      title: Text(group.name),
      subtitle: Text(
        group.active
            ? '${isClientList ? 'Lista de difusión' : 'Chat interno'} · '
                  '${group.members.length} ${isClientList ? (group.members.length == 1 ? 'cliente' : 'clientes') : (group.members.length == 1 ? 'miembro' : 'miembros')}'
            : 'Histórico · solo lectura · ${group.members.length} miembros',
      ),
      trailing: isAdmin && group.active
          ? PopupMenuButton<String>(
              key: Key('group-actions-${group.id}'),
              tooltip: isClientList
                  ? 'Acciones de la lista'
                  : 'Acciones del grupo',
              onSelected: (action) {
                if (action == 'edit') {
                  if (isClientList) {
                    _configureClientList(context, ref, group);
                  } else {
                    _configureStaffGroup(context, ref, group);
                  }
                } else if (action == 'avatar') {
                  _changeGroupAvatar(context, ref, group);
                } else if (action == 'delete-avatar') {
                  _deleteGroupAvatar(context, ref, group);
                } else if (action == 'delete') {
                  _deleteGroup(context, ref, group);
                }
              },
              itemBuilder: (_) => [
                PopupMenuItem(
                  value: 'edit',
                  child: ListTile(
                    leading: Icon(
                      isClientList
                          ? Icons.playlist_add_check
                          : Icons.manage_accounts_outlined,
                    ),
                    title: Text(isClientList ? 'Editar clientes' : 'Editar'),
                  ),
                ),
                if (!isClientList)
                  PopupMenuItem(
                    value: 'avatar',
                    child: ListTile(
                      leading: const Icon(Icons.add_a_photo_outlined),
                      title: Text(
                        group.avatarConfigured
                            ? 'Cambiar avatar'
                            : 'Añadir avatar',
                      ),
                    ),
                  ),
                if (!isClientList && group.avatarConfigured)
                  const PopupMenuItem(
                    value: 'delete-avatar',
                    child: ListTile(
                      leading: Icon(Icons.no_photography_outlined),
                      title: Text('Eliminar avatar'),
                    ),
                  ),
                PopupMenuItem(
                  value: 'delete',
                  child: ListTile(
                    leading: Icon(
                      isClientList
                          ? Icons.delete_outline
                          : Icons.archive_outlined,
                    ),
                    title: Text(
                      isClientList ? 'Eliminar lista' : 'Pasar a histórico',
                    ),
                  ),
                ),
              ],
            )
          : null,
      onTap: isClientList && isAdmin
          ? () => _configureClientList(context, ref, group)
          : group.threadId.isNotEmpty
          ? group.active && isAdmin
                ? () => _configureStaffGroup(context, ref, group)
                : () => context.go('/internal/${group.threadId}')
          : null,
    );
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
        title: Text(
          profile.isAdmin ? 'Grupos y listas de clientes' : 'Grupos internos',
        ),
        actions: [
          if (profile.isAdmin)
            IconButton(
              tooltip: 'Crear grupo o lista',
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
            data: (items) {
              final activeGroups = items.where(
                (group) => group.active && group.type == 'staff_chat',
              );
              final clientLists = items.where(
                (group) => group.active && group.type == 'client_list',
              );
              final historical = items.where(
                (group) => !group.active && group.type == 'staff_chat',
              );
              return [
                for (final group in activeGroups)
                  _groupTile(context, ref, group, profile.isAdmin),
                if (profile.isAdmin) ...[
                  const Padding(
                    padding: EdgeInsets.fromLTRB(16, 28, 16, 8),
                    child: Text(
                      'LISTAS DE CLIENTES',
                      key: Key('client-lists-section'),
                      style: TextStyle(fontWeight: FontWeight.bold),
                    ),
                  ),
                  if (clientLists.isEmpty)
                    const ListTile(
                      leading: Icon(Icons.playlist_add),
                      title: Text('Todavía no hay listas de clientes'),
                      subtitle: Text(
                        'Crea una lista para enviar una difusión a un segmento de clientes.',
                      ),
                    ),
                  for (final group in clientLists)
                    _groupTile(context, ref, group, profile.isAdmin),
                ],
                if (historical.isNotEmpty)
                  const Card(
                    margin: EdgeInsets.fromLTRB(12, 24, 12, 8),
                    child: ListTile(
                      key: Key('historical-groups-archive'),
                      leading: Icon(Icons.inventory_2_outlined),
                      title: Text('Archivo de grupos históricos'),
                      subtitle: Text(
                        'Conversaciones cerradas disponibles en modo de solo lectura.',
                      ),
                    ),
                  ),
                for (final group in historical)
                  _groupTile(context, ref, group, profile.isAdmin),
              ];
            },
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
