import 'package:file_picker/file_picker.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../../core/api/api_client.dart';
import '../../auth/presentation/auth_controller.dart';
import '../data/empleados_repository.dart';
import '../domain/empleado_despacho.dart';

final empleadosRepositoryProvider = Provider<EmpleadosRepository>(
  (ref) => EmpleadosRepository(ref.watch(apiClientProvider)),
);
final empleadosProvider = FutureProvider.autoDispose<List<EmpleadoDespacho>>(
  (ref) => ref.watch(empleadosRepositoryProvider).listar(),
);

class EmpleadosScreen extends ConsumerWidget {
  const EmpleadosScreen({super.key});

  Future<void> _editar(
    BuildContext context,
    WidgetRef ref, [
    EmpleadoDespacho? empleado,
  ]) async {
    final nombre = TextEditingController(text: empleado?.nombre ?? '');
    final email = TextEditingController(text: empleado?.email ?? '');
    final alias = TextEditingController(text: empleado?.aliasChat ?? '');
    var rol = empleado?.rol ?? 'empleado';
    var activo = empleado?.activo ?? true;
    final canales = {...?empleado?.canales};
    var guardando = false;

    final guardado = await showDialog<bool>(
      context: context,
      builder: (dialogContext) => StatefulBuilder(
        builder: (context, setState) => AlertDialog(
          title: Text(empleado == null ? 'Nuevo empleado' : 'Editar empleado'),
          content: SizedBox(
            width: 520,
            child: SingleChildScrollView(
              child: Column(
                mainAxisSize: MainAxisSize.min,
                children: [
                  TextField(
                    controller: nombre,
                    decoration: const InputDecoration(
                      labelText: 'Nombre completo',
                    ),
                  ),
                  const SizedBox(height: 10),
                  TextField(
                    controller: email,
                    keyboardType: TextInputType.emailAddress,
                    decoration: const InputDecoration(
                      labelText: 'Correo corporativo',
                    ),
                  ),
                  const SizedBox(height: 10),
                  TextField(
                    controller: alias,
                    decoration: const InputDecoration(
                      labelText: 'Nombre visible para clientes',
                      hintText: 'Ejemplo: Juan Jose',
                    ),
                  ),
                  const SizedBox(height: 14),
                  DropdownButtonFormField<String>(
                    initialValue: rol,
                    decoration: const InputDecoration(labelText: 'Rol'),
                    items: const [
                      DropdownMenuItem(
                        value: 'empleado',
                        child: Text('Empleado'),
                      ),
                      DropdownMenuItem(
                        value: 'admin',
                        child: Text('Administrador'),
                      ),
                    ],
                    onChanged: guardando
                        ? null
                        : (value) => setState(() => rol = value!),
                  ),
                  const SizedBox(height: 14),
                  Align(
                    alignment: Alignment.centerLeft,
                    child: Text(
                      'Canales',
                      style: Theme.of(context).textTheme.labelLarge,
                    ),
                  ),
                  Wrap(
                    spacing: 8,
                    children: [
                      for (final item in const [
                        ('laboral', 'Laboral'),
                        ('fiscal', 'Contable / Fiscal'),
                      ])
                        FilterChip(
                          label: Text(item.$2),
                          selected: canales.contains(item.$1),
                          onSelected: guardando
                              ? null
                              : (selected) => setState(
                                  () => selected
                                      ? canales.add(item.$1)
                                      : canales.remove(item.$1),
                                ),
                        ),
                    ],
                  ),
                  SwitchListTile(
                    contentPadding: EdgeInsets.zero,
                    title: const Text('Acceso activo'),
                    value: activo,
                    onChanged: guardando
                        ? null
                        : (value) => setState(() => activo = value),
                  ),
                ],
              ),
            ),
          ),
          actions: [
            TextButton(
              onPressed: guardando
                  ? null
                  : () => Navigator.pop(dialogContext, false),
              child: const Text('Cancelar'),
            ),
            FilledButton(
              onPressed: guardando
                  ? null
                  : () async {
                      if (nombre.text.trim().isEmpty ||
                          email.text.trim().isEmpty) {
                        return;
                      }
                      setState(() => guardando = true);
                      try {
                        final repository = ref.read(
                          empleadosRepositoryProvider,
                        );
                        if (empleado == null) {
                          await repository.crear(
                            nombre: nombre.text,
                            email: email.text,
                            rol: rol,
                            aliasChat: alias.text,
                            activo: activo,
                            canales: canales,
                          );
                        } else {
                          await repository.actualizar(
                            empleado.id,
                            nombre: nombre.text,
                            email: email.text,
                            rol: rol,
                            aliasChat: alias.text,
                            activo: activo,
                            canales: canales,
                          );
                        }
                        if (dialogContext.mounted) {
                          Navigator.pop(dialogContext, true);
                        }
                      } catch (error) {
                        if (context.mounted) {
                          ScaffoldMessenger.of(context).showSnackBar(
                            SnackBar(content: Text(apiErrorMessage(error))),
                          );
                          setState(() => guardando = false);
                        }
                      }
                    },
              child: guardando
                  ? const SizedBox.square(
                      dimension: 18,
                      child: CircularProgressIndicator(strokeWidth: 2),
                    )
                  : const Text('Guardar'),
            ),
          ],
        ),
      ),
    );
    nombre.dispose();
    email.dispose();
    alias.dispose();
    if (guardado == true) ref.invalidate(empleadosProvider);
  }

  Future<void> _subirAvatar(
    BuildContext context,
    WidgetRef ref,
    EmpleadoDespacho empleado,
  ) async {
    late final List<PlatformFile> result;
    try {
      result = await FilePicker.pickFiles(
        type: FileType.custom,
        allowedExtensions: ['jpg', 'jpeg', 'png', 'webp'],
      );
    } catch (error) {
      if (context.mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(
            content: Text('No se pudo abrir el selector de imagen.'),
          ),
        );
      }
      return;
    }
    if (result.isEmpty) return;
    try {
      await ref
          .read(empleadosRepositoryProvider)
          .subirAvatar(empleado.id, result.first);
      ref.invalidate(empleadosProvider);
    } catch (error) {
      if (context.mounted) {
        ScaffoldMessenger.of(
          context,
        ).showSnackBar(SnackBar(content: Text(apiErrorMessage(error))));
      }
    }
  }

  Future<void> _accion(
    BuildContext context,
    WidgetRef ref,
    EmpleadoDespacho empleado,
    String accion,
  ) async {
    if (accion == 'editar') {
      return _editar(context, ref, empleado);
    }
    if (accion == 'avatar') {
      return _subirAvatar(context, ref, empleado);
    }
    try {
      final repository = ref.read(empleadosRepositoryProvider);
      if (accion == 'quitar_avatar') {
        await repository.eliminarAvatar(empleado.id);
      }
      if (accion == 'revocar') {
        await repository.revocarSesiones(empleado.id);
      }
      ref.invalidate(empleadosProvider);
    } catch (error) {
      if (context.mounted) {
        ScaffoldMessenger.of(
          context,
        ).showSnackBar(SnackBar(content: Text(apiErrorMessage(error))));
      }
    }
  }

  Widget _avatar(EmpleadoDespacho empleado, String baseUrl, String token) {
    if (empleado.avatarConfigurado) {
      return CircleAvatar(
        backgroundImage: NetworkImage(
          '$baseUrl${empleado.avatarUrl}?v=${DateTime.now().millisecondsSinceEpoch}',
          headers: {'Authorization': 'Bearer $token'},
        ),
      );
    }
    final words = empleado.nombreVisible.trim().split(RegExp(r'\s+'));
    final initials = words
        .where((word) => word.isNotEmpty)
        .take(2)
        .map((word) => word[0])
        .join()
        .toUpperCase();
    return CircleAvatar(child: Text(initials.isEmpty ? '?' : initials));
  }

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final profile = ref.watch(sessionProvider).valueOrNull!.profile;
    if (!profile.isAdmin) {
      return Scaffold(
        appBar: AppBar(leading: BackButton(onPressed: () => context.go('/'))),
        body: const Center(child: Text('Se requiere acceso de administrador.')),
      );
    }
    final empleados = ref.watch(empleadosProvider);
    final api = ref.read(apiClientProvider);
    final baseUrl = api.dio.options.baseUrl.replaceAll(
      RegExp(r'/api/v1/messaging/?$'),
      '',
    );
    final token = ref.read(sessionProvider).valueOrNull?.token ?? '';
    return Scaffold(
      appBar: AppBar(
        leading: IconButton(
          onPressed: () => context.go('/'),
          icon: const Icon(Icons.arrow_back),
        ),
        title: const Text('Empleados del despacho'),
        actions: [
          IconButton(
            key: const Key('add-employee'),
            tooltip: 'Nuevo empleado',
            onPressed: () => _editar(context, ref),
            icon: const Icon(Icons.person_add_alt_1),
          ),
        ],
      ),
      body: empleados.when(
        loading: () => const Center(child: CircularProgressIndicator()),
        error: (error, _) => Center(
          child: FilledButton.icon(
            onPressed: () => ref.invalidate(empleadosProvider),
            icon: const Icon(Icons.refresh),
            label: const Text('Reintentar'),
          ),
        ),
        data: (items) => ListView.separated(
          padding: EdgeInsets.fromLTRB(
            12, 12, 12, 12 + MediaQuery.viewPaddingOf(context).bottom,
          ),
          itemCount: items.length,
          separatorBuilder: (_, _) => const Divider(height: 1),
          itemBuilder: (context, index) {
            final empleado = items[index];
            return ListTile(
              key: Key('employee-${empleado.id}'),
              contentPadding: const EdgeInsets.symmetric(
                horizontal: 8,
                vertical: 6,
              ),
              leading: _avatar(empleado, baseUrl, token),
              title: Text(empleado.nombreVisible),
              subtitle: Text(
                '${empleado.email}\n'
                '${empleado.rol == 'admin' ? 'Administrador' : 'Empleado'} · '
                '${empleado.canales.isEmpty ? 'Sin canales' : empleado.canales.join(', ')} · '
                '${empleado.vinculado ? 'Microsoft vinculado' : 'Pendiente de primer acceso'} · '
                '${empleado.online ? 'Activo' : 'Inactivo'}',
              ),
              isThreeLine: true,
              enabled: empleado.activo,
              trailing: PopupMenuButton<String>(
                onSelected: (value) => _accion(context, ref, empleado, value),
                itemBuilder: (_) => [
                  const PopupMenuItem(
                    value: 'editar',
                    child: Text('Editar permisos'),
                  ),
                  const PopupMenuItem(
                    value: 'avatar',
                    child: Text('Subir o cambiar avatar'),
                  ),
                  if (empleado.avatarConfigurado)
                    const PopupMenuItem(
                      value: 'quitar_avatar',
                      child: Text('Quitar avatar'),
                    ),
                  if (empleado.id != profile.id)
                    const PopupMenuItem(
                      value: 'revocar',
                      child: Text('Cerrar sus sesiones'),
                    ),
                ],
              ),
              onTap: () => _editar(context, ref, empleado),
            );
          },
        ),
      ),
    );
  }
}
