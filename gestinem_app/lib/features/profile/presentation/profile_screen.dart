import 'package:file_picker/file_picker.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../../core/api/api_client.dart';
import '../../../core/config/app_config.dart';
import '../../auth/domain/user_profile.dart';
import '../../auth/presentation/auth_controller.dart';
import '../../messaging/presentation/messaging_providers.dart';

class ProfileScreen extends ConsumerStatefulWidget {
  const ProfileScreen({super.key});

  @override
  ConsumerState<ProfileScreen> createState() => _ProfileScreenState();
}

class _ProfileScreenState extends ConsumerState<ProfileScreen> {
  late TextEditingController _aliasController;
  bool _editingAlias = false;
  bool _uploadingAvatar = false;
  String? _localAvatarUrl;
  String? _error;

  @override
  void initState() {
    super.initState();
    final profile = ref.read(sessionProvider).valueOrNull!.profile;
    _aliasController = TextEditingController(text: profile.name);
  }

  @override
  void dispose() {
    _aliasController.dispose();
    super.dispose();
  }

  Future<void> _pickAndUploadAvatar() async {
    late final List<PlatformFile> result;
    try {
      result = await FilePicker.pickFiles(
        type: FileType.custom,
        allowedExtensions: ['jpg', 'jpeg', 'png', 'webp'],
      );
    } catch (error) {
      if (mounted) {
        setState(() => _error = 'No se pudo abrir el selector de imagen.');
      }
      return;
    }
    if (result.isEmpty) return;
    setState(() {
      _uploadingAvatar = true;
      _error = null;
    });
    try {
      final url = await ref
          .read(profileRepositoryProvider)
          .uploadAvatar(result.first);
      setState(() {
        _localAvatarUrl = url.isNotEmpty
            ? '$url?v=${DateTime.now().millisecondsSinceEpoch}'
            : null;
      });
      await ref.read(sessionProvider.notifier).refreshProfile();
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(content: Text('Avatar actualizado correctamente')),
        );
      }
    } catch (e) {
      if (mounted) setState(() => _error = apiErrorMessage(e));
    } finally {
      if (mounted) setState(() => _uploadingAvatar = false);
    }
  }

  Future<void> _saveAlias() async {
    final alias = _aliasController.text.trim();
    if (alias.isEmpty) return;
    try {
      await ref.read(profileRepositoryProvider).updateChatAlias(alias);
      await ref.read(sessionProvider.notifier).refreshProfile();
      setState(() => _editingAlias = false);
      if (mounted) {
        ScaffoldMessenger.of(
          context,
        ).showSnackBar(const SnackBar(content: Text('Nombre actualizado')));
      }
    } catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(
          context,
        ).showSnackBar(SnackBar(content: Text(apiErrorMessage(e))));
      }
    }
  }

  Widget _buildAvatar(UserProfile profile, String baseUrl) {
    final avatarUrl = _localAvatarUrl ?? profile.avatarUrl;
    if (avatarUrl.isNotEmpty) {
      return CircleAvatar(
        radius: 48,
        backgroundImage: NetworkImage(
          '$baseUrl$avatarUrl',
          headers: {
            'Authorization':
                'Bearer ${ref.read(sessionProvider).valueOrNull?.token ?? ''}',
          },
        ),
      );
    }
    final initials = profile.name.isEmpty
        ? '?'
        : profile.name
              .split(' ')
              .take(2)
              .map((w) => w.isEmpty ? '' : w[0])
              .join()
              .toUpperCase();
    return CircleAvatar(
      radius: 48,
      child: Text(initials, style: const TextStyle(fontSize: 28)),
    );
  }

  @override
  Widget build(BuildContext context) {
    final profile = ref.watch(sessionProvider).valueOrNull!.profile;
    final baseUrl = appConfig.apiBaseUrl.replaceAll('/api/v1/messaging', '');

    return Scaffold(
      appBar: AppBar(
        leading: IconButton(
          onPressed: () => context.go('/'),
          icon: const Icon(Icons.arrow_back),
        ),
        title: const Text('Mi perfil'),
      ),
      body: Center(
        child: ConstrainedBox(
          constraints: const BoxConstraints(maxWidth: 560),
          child: ListView(
            padding: const EdgeInsets.all(24),
            children: [
              Center(
                child: Stack(
                  alignment: Alignment.bottomRight,
                  children: [
                    _uploadingAvatar
                        ? const CircleAvatar(
                            radius: 48,
                            child: CircularProgressIndicator(strokeWidth: 3),
                          )
                        : _buildAvatar(profile, baseUrl),
                    if (profile.type == UserType.staff)
                      InkWell(
                        onTap: _uploadingAvatar ? null : _pickAndUploadAvatar,
                        child: Container(
                          padding: const EdgeInsets.all(6),
                          decoration: BoxDecoration(
                            color: Theme.of(context).colorScheme.primary,
                            shape: BoxShape.circle,
                          ),
                          child: const Icon(
                            Icons.camera_alt,
                            size: 18,
                            color: Colors.white,
                          ),
                        ),
                      ),
                  ],
                ),
              ),
              if (_error != null) ...[
                const SizedBox(height: 8),
                Text(
                  _error!,
                  textAlign: TextAlign.center,
                  style: TextStyle(color: Theme.of(context).colorScheme.error),
                ),
              ],
              const SizedBox(height: 20),
              if (profile.type == UserType.staff) ...[
                _editingAlias
                    ? Row(
                        children: [
                          Expanded(
                            child: TextField(
                              controller: _aliasController,
                              decoration: const InputDecoration(
                                labelText: 'Nombre visible',
                              ),
                            ),
                          ),
                          IconButton(
                            onPressed: _saveAlias,
                            icon: const Icon(Icons.check),
                          ),
                          IconButton(
                            onPressed: () =>
                                setState(() => _editingAlias = false),
                            icon: const Icon(Icons.close),
                          ),
                        ],
                      )
                    : ListTile(
                        leading: const Icon(Icons.person_outline),
                        title: const Text('Nombre visible'),
                        subtitle: Text(profile.name),
                        trailing: IconButton(
                          onPressed: () => setState(() => _editingAlias = true),
                          icon: const Icon(Icons.edit_outlined),
                        ),
                      ),
              ] else ...[
                Text(
                  profile.name,
                  textAlign: TextAlign.center,
                  style: Theme.of(context).textTheme.headlineSmall,
                ),
              ],
              Text(profile.email, textAlign: TextAlign.center),
              const SizedBox(height: 20),
              ListTile(
                leading: const Icon(Icons.badge_outlined),
                title: const Text('Tipo de acceso'),
                subtitle: Text(profile.type.name),
              ),
              if (profile.staffRole != null)
                ListTile(
                  leading: const Icon(Icons.admin_panel_settings_outlined),
                  title: const Text('Rol'),
                  subtitle: Text(profile.staffRole!.name),
                ),
              if (profile.channels.isNotEmpty)
                ListTile(
                  leading: const Icon(Icons.category_outlined),
                  title: const Text('Canales'),
                  subtitle: Text(profile.channels.join(', ')),
                ),
              ListTile(
                leading: const Icon(Icons.info_outline),
                title: const Text('Acerca de Gestinem'),
                subtitle: const Text('Versión y actualizaciones'),
                onTap: () => context.push('/about'),
              ),
              const SizedBox(height: 20),
              FilledButton.tonalIcon(
                onPressed: () => ref.read(sessionProvider.notifier).logout(),
                icon: const Icon(Icons.logout),
                label: const Text('Cerrar sesión'),
              ),
            ],
          ),
        ),
      ),
    );
  }
}
