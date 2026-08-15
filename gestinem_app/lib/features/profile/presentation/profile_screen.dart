import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../auth/presentation/auth_controller.dart';

class ProfileScreen extends ConsumerWidget {
  const ProfileScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final profile = ref.watch(sessionProvider).valueOrNull!.profile;
    return Scaffold(
      appBar: AppBar(leading: IconButton(onPressed: () => context.go('/'), icon: const Icon(Icons.arrow_back)), title: const Text('Perfil')),
      body: Center(child: ConstrainedBox(constraints: const BoxConstraints(maxWidth: 560), child: ListView(padding: const EdgeInsets.all(24), children: [
        CircleAvatar(radius: 42, child: Text(profile.name.isEmpty ? '?' : profile.name[0], style: const TextStyle(fontSize: 30))),
        const SizedBox(height: 18),
        Text(profile.name, textAlign: TextAlign.center, style: Theme.of(context).textTheme.headlineSmall),
        Text(profile.email, textAlign: TextAlign.center),
        const SizedBox(height: 20),
        ListTile(leading: const Icon(Icons.badge_outlined), title: const Text('Tipo de acceso'), subtitle: Text(profile.type.name)),
        if (profile.staffRole != null) ListTile(leading: const Icon(Icons.admin_panel_settings_outlined), title: const Text('Rol'), subtitle: Text(profile.staffRole!.name)),
        if (profile.channels.isNotEmpty) ListTile(leading: const Icon(Icons.category_outlined), title: const Text('Canales'), subtitle: Text(profile.channels.join(', '))),
        const SizedBox(height: 20),
        FilledButton.tonalIcon(onPressed: () => ref.read(sessionProvider.notifier).logout(), icon: const Icon(Icons.logout), label: const Text('Cerrar sesion')),
      ]))),
    );
  }
}
