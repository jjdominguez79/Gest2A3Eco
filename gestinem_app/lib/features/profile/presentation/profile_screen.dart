import 'package:file_picker/file_picker.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../../core/api/api_client.dart';
import '../../../core/config/app_config.dart';
import '../../../core/widgets/authenticated_avatar.dart';
import '../../auth/domain/user_profile.dart';
import '../../auth/presentation/auth_controller.dart';
import '../../company_profile/domain/company_profile.dart';
import '../../company_profile/domain/profile_change_request.dart';
import '../../company_profile/presentation/company_profile_providers.dart';
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
    if (profile.type == UserType.client) {
      return _ClientAreaScreen(profile: profile);
    }
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
            padding: EdgeInsets.fromLTRB(
              24,
              24,
              24,
              24 + MediaQuery.viewPaddingOf(context).bottom,
            ),
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

class _ClientAreaScreen extends ConsumerWidget {
  const _ClientAreaScreen({required this.profile});

  final UserProfile profile;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final company = ref.watch(companyProfileProvider);
    final requests = ref.watch(profileChangeRequestsProvider);
    return Scaffold(
      appBar: AppBar(
        leading: IconButton(
          onPressed: () => context.go('/'),
          icon: const Icon(Icons.arrow_back),
        ),
        title: const Text('Mi área'),
      ),
      body: SafeArea(
        top: false,
        child: RefreshIndicator(
          onRefresh: () async {
            ref.invalidate(companyProfileProvider);
            ref.invalidate(profileChangeRequestsProvider);
            await ref.read(companyProfileProvider.future);
          },
          child: company.when(
            loading: () => const Center(child: CircularProgressIndicator()),
            error: (error, _) => ListView(
              children: [
                const SizedBox(height: 120),
                Center(child: Text(apiErrorMessage(error))),
              ],
            ),
            data: (value) => _ClientAreaContent(
              user: profile,
              company: value,
              requests: requests,
            ),
          ),
        ),
      ),
    );
  }
}

class _ClientAreaContent extends ConsumerWidget {
  const _ClientAreaContent({
    required this.user,
    required this.company,
    required this.requests,
  });

  final UserProfile user;
  final CompanyProfile company;
  final AsyncValue<List<ProfileChangeRequest>> requests;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final theme = Theme.of(context);
    return ListView(
      physics: const AlwaysScrollableScrollPhysics(),
      padding: EdgeInsets.fromLTRB(
        16,
        16,
        16,
        24 + MediaQuery.viewPaddingOf(context).bottom,
      ),
      children: [
        Center(
          child: Stack(
            alignment: Alignment.bottomRight,
            children: [
              AuthenticatedAvatar(
                key: const Key('company-logo-avatar'),
                radius: 48,
                baseUrl: appConfig.apiBaseUrl.replaceAll(
                  RegExp(r'/api/v1/messaging/?$'),
                  '',
                ),
                authToken: ref.read(sessionProvider).valueOrNull?.token ?? '',
                imagePath: company.logoUrl ?? '',
                fallbackText: _companyInitials(company),
                cacheVersion: company.profileSyncedAt ?? company.name,
              ),
              Material(
                color: theme.colorScheme.primary,
                shape: const CircleBorder(),
                child: IconButton(
                  key: const Key('request-company-logo-button'),
                  tooltip: 'Añadir o cambiar logotipo',
                  onPressed: () =>
                      context.push('/company-profile/change-request'),
                  icon: const Icon(
                    Icons.camera_alt,
                    size: 18,
                    color: Colors.white,
                  ),
                ),
              ),
            ],
          ),
        ),
        const SizedBox(height: 12),
        Text(
          company.legalName ?? company.name,
          textAlign: TextAlign.center,
          style: theme.textTheme.headlineSmall,
        ),
        Text(
          'Conectado como: ${user.name}',
          textAlign: TextAlign.center,
          style: theme.textTheme.bodyMedium?.copyWith(
            color: theme.colorScheme.onSurfaceVariant,
          ),
        ),
        const SizedBox(height: 20),
        _AreaCard(
          title: 'Mi usuario',
          icon: Icons.person_outline,
          children: [
            _AreaRow(label: 'Nombre', value: user.name),
            _AreaRow(label: 'Correo de acceso', value: user.email),
            const _AreaRow(label: 'Tipo de acceso', value: 'Cliente'),
          ],
        ),
        const SizedBox(height: 10),
        _AreaCard(
          title: 'Mi empresa',
          icon: Icons.business_outlined,
          children: [
            if (company.taxId?.isNotEmpty == true)
              _AreaRow(label: 'NIF/CIF', value: company.taxId!),
            if (company.address?.isNotEmpty == true)
              _AreaRow(label: 'Dirección', value: company.address!),
            if (_location(company).isNotEmpty)
              _AreaRow(label: 'Localidad', value: _location(company)),
            if (company.phone?.isNotEmpty == true)
              _AreaRow(label: 'Teléfono', value: company.phone!),
            if (company.email?.isNotEmpty == true)
              _AreaRow(label: 'Correo', value: company.email!),
            const SizedBox(height: 8),
            FilledButton.icon(
              key: const Key('request-profile-change-button'),
              onPressed: () => context.push('/company-profile/change-request'),
              icon: const Icon(Icons.edit_note_outlined),
              label: const Text('Solicitar modificación'),
            ),
          ],
        ),
        const SizedBox(height: 10),
        _RequestsCard(requests: requests),
        const SizedBox(height: 10),
        Card(
          child: Column(
            children: [
              ListTile(
                leading: const Icon(Icons.info_outline),
                title: const Text('Acerca de Gestinem'),
                subtitle: const Text('Versión y actualizaciones'),
                onTap: () => context.push('/about'),
              ),
              const Divider(height: 1),
              ListTile(
                leading: const Icon(Icons.logout),
                title: const Text('Cerrar sesión'),
                onTap: () => ref.read(sessionProvider.notifier).logout(),
              ),
            ],
          ),
        ),
      ],
    );
  }

  static String _location(CompanyProfile company) {
    return [
      company.postalCode,
      company.city,
      company.province,
      company.country,
    ].whereType<String>().where((value) => value.isNotEmpty).join(' · ');
  }

  static String _companyInitials(CompanyProfile company) {
    final name = company.legalName ?? company.name;
    return name
        .split(RegExp(r'\s+'))
        .where((part) => part.isNotEmpty)
        .take(2)
        .map((part) => part[0])
        .join()
        .toUpperCase();
  }
}

class _AreaCard extends StatelessWidget {
  const _AreaCard({
    required this.title,
    required this.icon,
    required this.children,
  });

  final String title;
  final IconData icon;
  final List<Widget> children;

  @override
  Widget build(BuildContext context) {
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                Icon(icon),
                const SizedBox(width: 8),
                Text(title, style: Theme.of(context).textTheme.titleMedium),
              ],
            ),
            const SizedBox(height: 12),
            ...children,
          ],
        ),
      ),
    );
  }
}

class _AreaRow extends StatelessWidget {
  const _AreaRow({required this.label, required this.value});

  final String label;
  final String value;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 4),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          SizedBox(
            width: 125,
            child: Text(
              label,
              style: TextStyle(
                color: Theme.of(context).colorScheme.onSurfaceVariant,
              ),
            ),
          ),
          Expanded(child: Text(value)),
        ],
      ),
    );
  }
}

class _RequestsCard extends StatelessWidget {
  const _RequestsCard({required this.requests});

  final AsyncValue<List<ProfileChangeRequest>> requests;

  @override
  Widget build(BuildContext context) {
    return _AreaCard(
      title: 'Solicitudes',
      icon: Icons.pending_actions_outlined,
      children: [
        requests.when(
          loading: () => const LinearProgressIndicator(),
          error: (_, _) => const Text('No se pudo cargar el historial.'),
          data: (items) {
            if (items.isEmpty) {
              return const Text('No hay solicitudes de modificación.');
            }
            return Column(
              children: items
                  .take(5)
                  .map((item) {
                    final status = switch (item.status) {
                      'applied' => 'Aplicada',
                      'rejected' => 'Rechazada',
                      _ => 'Pendiente de revisión',
                    };
                    return ListTile(
                      contentPadding: EdgeInsets.zero,
                      leading: Icon(
                        item.isPending
                            ? Icons.schedule_outlined
                            : item.status == 'applied'
                            ? Icons.check_circle_outline
                            : Icons.cancel_outlined,
                      ),
                      title: Text(status),
                      subtitle: Text(
                        item.changes.isEmpty
                            ? 'Cambio de logotipo'
                            : '${item.changes.length} dato(s) solicitado(s)',
                      ),
                    );
                  })
                  .toList(growable: false),
            );
          },
        ),
      ],
    );
  }
}
