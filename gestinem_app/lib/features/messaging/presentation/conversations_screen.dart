import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../../core/api/api_client.dart';
import '../../../core/storage/hidden_conversations_storage.dart';
import '../../../core/widgets/authenticated_avatar.dart';
import '../../auth/domain/user_profile.dart';
import '../../auth/presentation/auth_controller.dart';
import '../domain/conversation.dart';
import 'conversation_screen.dart';
import 'messaging_providers.dart';

final hiddenConversationsStorageProvider = Provider<HiddenConversationsStorage>(
  (ref) => HiddenConversationsStorage(),
);

class ConversationsScreen extends ConsumerStatefulWidget {
  const ConversationsScreen({super.key});

  @override
  ConsumerState<ConversationsScreen> createState() =>
      _ConversationsScreenState();
}

class _ConversationsScreenState extends ConsumerState<ConversationsScreen>
    with WidgetsBindingObserver {
  final _search = TextEditingController();
  String _channel = 'todos';
  String? _selected;
  bool _selectedInternal = false;
  Map<String, DateTime> _hiddenGroups = {};

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addObserver(this);
    WidgetsBinding.instance.addPostFrameCallback((_) {
      unawaited(_loadHiddenGroups());
    });
  }

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    if (state == AppLifecycleState.resumed) _refreshMessaging();
  }

  void _refreshMessaging([String? conversationId]) {
    ref.invalidate(conversationsProvider);
    ref.invalidate(unifiedConversationProvider);
    ref.invalidate(unifiedMessagesProvider);
    if (conversationId != null && conversationId.isNotEmpty) {
      ref.invalidate(messagesProvider(conversationId));
    }
  }

  Future<void> _loadHiddenGroups() async {
    final profile = ref.read(sessionProvider).valueOrNull?.profile;
    if (profile == null || profile.type != UserType.staff) return;
    final hidden = await ref
        .read(hiddenConversationsStorageProvider)
        .read(profile.id);
    if (mounted) setState(() => _hiddenGroups = hidden);
  }

  bool _isHidden(ClientGroup group) {
    final hiddenAt = _hiddenGroups[group.companyCode];
    if (hiddenAt == null) return false;
    final updatedAt = group.updatedAt;
    return updatedAt == null || !updatedAt.toUtc().isAfter(hiddenAt);
  }

  Future<void> _hideGroup(ClientGroup group) async {
    final profile = ref.read(sessionProvider).valueOrNull!.profile;
    final updatedAt = group.updatedAt ?? DateTime.now();
    await ref
        .read(hiddenConversationsStorageProvider)
        .hide(profile.id, group.companyCode, updatedAt);
    if (mounted) {
      setState(() {
        _hiddenGroups = {
          ..._hiddenGroups,
          group.companyCode: updatedAt.toUtc(),
        };
        if (group.conversations.any(
          (conversation) => conversation.id == _selected,
        )) {
          _selected = null;
        }
      });
    }
  }

  @override
  void dispose() {
    WidgetsBinding.instance.removeObserver(this);
    _search.dispose();
    super.dispose();
  }

  void _navigateToConversation(String id) {
    final wide = MediaQuery.sizeOf(context).width >= 900;
    if (wide) {
      setState(() {
        _selected = id;
        _selectedInternal = false;
      });
    } else {
      context.go('/conversation/$id');
    }
  }

  void _navigateToInternal(String id) {
    final wide = MediaQuery.sizeOf(context).width >= 900;
    if (wide) {
      setState(() {
        _selected = id;
        _selectedInternal = true;
      });
    } else {
      context.go('/internal/$id');
    }
  }

  void _selectChannel(BuildContext context, ClientGroup group) {
    if (group.conversations.length == 1) {
      _navigateToConversation(group.conversations.first.id);
      return;
    }
    showModalBottomSheet(
      context: context,
      builder: (ctx) => SafeArea(
        child: Wrap(
          children: [
            Padding(
              padding: const EdgeInsets.all(16),
              child: Text(
                'Selecciona canal',
                style: Theme.of(ctx).textTheme.titleMedium,
              ),
            ),
            for (final conv in group.conversations)
              ListTile(
                leading: _ChannelChip(kind: conv.kind),
                title: Text(_channelLabel(conv.kind)),
                trailing: conv.unreadCount > 0
                    ? Badge(label: Text('${conv.unreadCount}'))
                    : null,
                onTap: () {
                  Navigator.pop(ctx);
                  _navigateToConversation(conv.id);
                },
              ),
          ],
        ),
      ),
    );
  }

  Future<bool?> _confirmHide(BuildContext context) => showDialog<bool>(
    context: context,
    builder: (ctx) => AlertDialog(
      title: const Text('Ocultar conversaciones'),
      content: const Text(
        'Se ocultarán solo en este dispositivo. Volverán a aparecer cuando llegue un mensaje nuevo.',
      ),
      actions: [
        TextButton(
          onPressed: () => Navigator.pop(ctx, false),
          child: const Text('Cancelar'),
        ),
        FilledButton(
          onPressed: () => Navigator.pop(ctx, true),
          child: const Text('Ocultar'),
        ),
      ],
    ),
  );

  Future<void> _toggleRead(ClientGroup group) async {
    final profile = ref.read(sessionProvider).valueOrNull!.profile;
    final repo = ref.read(messagingRepositoryProvider);
    final hasUnread = group.totalUnread > 0;
    try {
      for (final conv in group.conversations) {
        if (hasUnread) {
          await repo.markRead(profile, conv.id);
        } else {
          await repo.markUnread(profile, conv.id);
        }
      }
      ref.invalidate(conversationsProvider);
    } catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(
            content: Text('No se pudo actualizar el estado de lectura'),
          ),
        );
      }
    }
  }

  Future<void> _setClientAccess(ClientGroup group, bool active) async {
    if (!active) {
      final confirmed = await showDialog<bool>(
        context: context,
        builder: (dialogContext) => AlertDialog(
          title: const Text('Desactivar acceso del cliente'),
          content: Text(
            '${group.displayName} dejará de poder iniciar sesión y se cerrarán sus sesiones activas. El historial no se borrará.',
          ),
          actions: [
            TextButton(
              onPressed: () => Navigator.pop(dialogContext, false),
              child: const Text('Cancelar'),
            ),
            FilledButton(
              onPressed: () => Navigator.pop(dialogContext, true),
              child: const Text('Desactivar'),
            ),
          ],
        ),
      );
      if (confirmed != true) return;
    }
    try {
      await ref
          .read(messagingRepositoryProvider)
          .setClientAccess(group.companyCode, active);
      ref.invalidate(conversationsProvider);
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(
            content: Text(
              active
                  ? 'Acceso del cliente activado'
                  : 'Acceso del cliente desactivado',
            ),
          ),
        );
      }
    } catch (error) {
      if (mounted) {
        ScaffoldMessenger.of(
          context,
        ).showSnackBar(SnackBar(content: Text(apiErrorMessage(error))));
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    final profile = ref.watch(sessionProvider).valueOrNull!.profile;
    final conversations = ref.watch(conversationsProvider);
    if (profile.type == UserType.client) {
      return _buildClientScreen(profile, conversations);
    }
    final internalThreads = ref.watch(internalThreadsProvider);
    final channelOptions = profile.isAdmin
        ? const ['todos', 'laboral', 'fiscal', 'private']
        : profile.channels
              .where((channel) => {'laboral', 'fiscal'}.contains(channel))
              .toList(growable: false);
    final effectiveChannel = channelOptions.contains(_channel)
        ? _channel
        : (channelOptions.isEmpty ? '' : channelOptions.first);
    final quickThreads = profile.isAdmin
        ? const <InternalThread>[]
        : (internalThreads.valueOrNull ?? const <InternalThread>[])
              .where(
                (thread) =>
                    (thread.kind == 'group' && thread.channel.isEmpty) ||
                    thread.kind == 'direct',
              )
              .toList(growable: false);
    final apiBaseUrl = ref
        .read(apiClientProvider)
        .dio
        .options
        .baseUrl
        .replaceAll(RegExp(r'/api/v1/messaging/?$'), '');
    final authToken = ref.read(sessionProvider).valueOrNull?.token ?? '';
    final wide = MediaQuery.sizeOf(context).width >= 900;
    return Scaffold(
      appBar: AppBar(
        title: Text(profile.name, maxLines: 1, overflow: TextOverflow.ellipsis),
        actions: [
          if (profile.isAdmin)
            IconButton(
              key: const Key('invite-client-button'),
              tooltip: 'Invitar cliente',
              onPressed: () => context.go('/invite-client'),
              icon: const Icon(Icons.person_add_alt_1),
            ),
          IconButton(
            onPressed: () => ref.invalidate(conversationsProvider),
            icon: const Icon(Icons.refresh),
          ),
          IconButton(
            key: const Key('staff-profile-button'),
            tooltip: 'Mi perfil',
            onPressed: () => context.go('/profile'),
            icon: _ProfileAvatar(profile: profile, radius: 17),
          ),
        ],
      ),
      drawer: _AppDrawer(profile: profile),
      body: Row(
        children: [
          SizedBox(
            width: wide ? 380 : MediaQuery.sizeOf(context).width,
            child: Column(
              children: [
                Padding(
                  padding: const EdgeInsets.fromLTRB(12, 12, 12, 6),
                  child: TextField(
                    controller: _search,
                    decoration: const InputDecoration(
                      prefixIcon: Icon(Icons.search),
                      hintText: 'Buscar por código o nombre',
                    ),
                    onChanged: (_) => setState(() {}),
                  ),
                ),
                SizedBox(
                  height: 46,
                  child: ListView(
                    scrollDirection: Axis.horizontal,
                    padding: const EdgeInsets.symmetric(horizontal: 10),
                    children: [
                      for (final channel in channelOptions)
                        Padding(
                          padding: const EdgeInsets.symmetric(horizontal: 3),
                          child: ChoiceChip(
                            label: Text(switch (channel) {
                              'todos' => 'Todos',
                              'laboral' => 'LA',
                              'fiscal' => 'CF',
                              'private' => 'Directo',
                              _ => channel,
                            }),
                            selected:
                                !_selectedInternal &&
                                effectiveChannel == channel,
                            onSelected: (_) => setState(() {
                              _channel = channel;
                              _selectedInternal = false;
                            }),
                          ),
                        ),
                      for (final thread in quickThreads)
                        Padding(
                          padding: const EdgeInsets.symmetric(horizontal: 3),
                          child: ActionChip(
                            avatar: thread.kind == 'direct'
                                ? AuthenticatedAvatar(
                                    radius: 12,
                                    baseUrl: apiBaseUrl,
                                    authToken: authToken,
                                    imagePath: thread.counterpartAvatarUrl,
                                    fallbackText: _initials(thread.title),
                                    cacheVersion: thread.id,
                                  )
                                : const Icon(Icons.groups_outlined, size: 18),
                            label: Text(
                              thread.kind == 'direct'
                                  ? 'Administrador'
                                  : thread.title,
                            ),
                            onPressed: () => _navigateToInternal(thread.id),
                          ),
                        ),
                    ],
                  ),
                ),
                Expanded(
                  child: conversations.when(
                    loading: () =>
                        const Center(child: CircularProgressIndicator()),
                    error: (error, _) => Center(
                      child: Text(
                        'No se pudieron cargar las conversaciones.\n$error',
                        textAlign: TextAlign.center,
                      ),
                    ),
                    data: (items) {
                      final query = _search.text.trim().toLowerCase();

                      // Para staff: agrupar por cliente
                      if (profile.type == UserType.staff) {
                        var filtered = items.where((item) {
                          final channelMatches =
                              effectiveChannel == 'todos' ||
                              item.kind == effectiveChannel;
                          final searchMatches =
                              query.isEmpty ||
                              item.companyCode.toLowerCase().contains(query) ||
                              item.companyName.toLowerCase().contains(query);
                          return channelMatches && searchMatches;
                        }).toList();

                        final groups = groupConversationsByClient(
                          filtered,
                        ).where((group) => !_isHidden(group)).toList();
                        if (groups.isEmpty) {
                          return const Center(
                            child: Text('No hay conversaciones'),
                          );
                        }
                        return RefreshIndicator(
                          onRefresh: () async =>
                              ref.invalidate(conversationsProvider),
                          child: ListView.builder(
                            key: const Key('conversation-list'),
                            itemCount: groups.length,
                            itemBuilder: (context, index) {
                              final group = groups[index];
                              return Dismissible(
                                key: Key('swipe-group-${group.companyCode}'),
                                direction: DismissDirection.horizontal,
                                confirmDismiss: (direction) async {
                                  if (direction ==
                                      DismissDirection.startToEnd) {
                                    if (!profile.isAdmin) return false;
                                    final confirmed = await _confirmHide(
                                      context,
                                    );
                                    if (confirmed == true) {
                                      await _hideGroup(group);
                                    }
                                    return false;
                                  } else {
                                    await _toggleRead(group);
                                    return false;
                                  }
                                },
                                background: Container(
                                  color: Colors.orange,
                                  alignment: Alignment.centerLeft,
                                  padding: const EdgeInsets.symmetric(
                                    horizontal: 20,
                                  ),
                                  child: const Icon(
                                    Icons.visibility_off_outlined,
                                    color: Colors.white,
                                  ),
                                ),
                                secondaryBackground: Container(
                                  color: Colors.blue,
                                  alignment: Alignment.centerRight,
                                  padding: const EdgeInsets.symmetric(
                                    horizontal: 20,
                                  ),
                                  child: const Icon(
                                    Icons.mark_chat_read_outlined,
                                    color: Colors.white,
                                  ),
                                ),
                                child: _ClientGroupTile(
                                  group: group,
                                  selected: group.conversations.any(
                                    (c) => c.id == _selected,
                                  ),
                                  onTap: () => _selectChannel(context, group),
                                  onAccessChanged: profile.isAdmin
                                      ? (active) =>
                                            _setClientAccess(group, active)
                                      : null,
                                ),
                              );
                            },
                          ),
                        );
                      }

                      return const SizedBox.shrink();
                    },
                  ),
                ),
              ],
            ),
          ),
          if (wide) ...[
            const VerticalDivider(width: 1),
            Expanded(
              child: _selected == null
                  ? const Center(
                      child: Column(
                        mainAxisSize: MainAxisSize.min,
                        children: [
                          Icon(Icons.forum_outlined, size: 58),
                          SizedBox(height: 12),
                          Text('Selecciona una conversación'),
                        ],
                      ),
                    )
                  : ConversationView(
                      conversationId: _selected!,
                      internal: _selectedInternal,
                      showInternalHeader: _selectedInternal,
                    ),
            ),
          ],
        ],
      ),
    );
  }

  Widget _buildClientScreen(
    UserProfile profile,
    AsyncValue<List<Conversation>> conversations,
  ) => Scaffold(
    appBar: AppBar(
      toolbarHeight: 72,
      titleSpacing: 16,
      title: Row(
        children: [
          Image.asset(
            'assets/images/logo.png',
            height: 38,
            semanticLabel: 'Gestinem',
          ),
          const SizedBox(width: 12),
          const Expanded(
            child: Column(
              mainAxisSize: MainAxisSize.min,
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text('Gestinem', style: TextStyle(fontWeight: FontWeight.w700)),
                Text(
                  'Asesoría fiscal, contable y laboral',
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                  style: TextStyle(fontSize: 12, fontWeight: FontWeight.w400),
                ),
              ],
            ),
          ),
        ],
      ),
      actions: [
        IconButton(
          key: const Key('client-profile-button'),
          tooltip: 'Mi perfil',
          onPressed: () => context.go('/profile'),
          icon: _ProfileAvatar(profile: profile, radius: 17),
        ),
        const SizedBox(width: 8),
      ],
    ),
    body: conversations.when(
      loading: () => const Center(child: CircularProgressIndicator()),
      error: (error, _) => Center(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            const Text('No se pudieron cargar los canales.'),
            const SizedBox(height: 12),
            FilledButton.icon(
              onPressed: () => ref.invalidate(conversationsProvider),
              icon: const Icon(Icons.refresh),
              label: const Text('Reintentar'),
            ),
          ],
        ),
      ),
      data: (items) {
        final channels = [...items]
          ..sort(
            (a, b) => _clientChannelOrder(
              a.kind,
            ).compareTo(_clientChannelOrder(b.kind)),
          );
        if (channels.isEmpty) {
          return const Center(child: Text('No hay canales disponibles.'));
        }
        final selected = channels.any((item) => item.id == _selected)
            ? channels.firstWhere((item) => item.id == _selected)
            : channels.first;
        return Column(
          children: [
            _ClientChannelSelector(
              conversations: channels,
              selectedId: selected.id,
              baseUrl: ref
                  .read(apiClientProvider)
                  .dio
                  .options
                  .baseUrl
                  .replaceAll(RegExp(r'/api/v1/messaging/?$'), ''),
              authToken: ref.read(sessionProvider).valueOrNull?.token ?? '',
              onSelected: (id) => setState(() => _selected = id),
            ),
            const Divider(height: 1),
            Expanded(
              child: ConversationView(
                key: ValueKey('client-conversation-${selected.id}'),
                conversationId: selected.id,
              ),
            ),
          ],
        );
      },
    ),
  );
}

class _ClientChannelSelector extends StatelessWidget {
  const _ClientChannelSelector({
    required this.conversations,
    required this.selectedId,
    required this.baseUrl,
    required this.authToken,
    required this.onSelected,
  });

  final List<Conversation> conversations;
  final String selectedId;
  final String baseUrl;
  final String authToken;
  final ValueChanged<String> onSelected;

  @override
  Widget build(BuildContext context) {
    final colors = Theme.of(context).colorScheme;
    return Material(
      color: colors.surface,
      child: SafeArea(
        bottom: false,
        child: Padding(
          padding: const EdgeInsets.fromLTRB(10, 10, 10, 12),
          child: Row(
            children: [
              for (final conversation in conversations)
                Expanded(
                  child: Padding(
                    padding: const EdgeInsets.symmetric(horizontal: 4),
                    child: InkWell(
                      key: Key('client-channel-${conversation.kind}'),
                      borderRadius: BorderRadius.circular(16),
                      onTap: () => onSelected(conversation.id),
                      child: AnimatedContainer(
                        duration: const Duration(milliseconds: 180),
                        padding: const EdgeInsets.symmetric(
                          horizontal: 6,
                          vertical: 9,
                        ),
                        decoration: BoxDecoration(
                          color: conversation.id == selectedId
                              ? colors.primaryContainer
                              : colors.surfaceContainerLow,
                          borderRadius: BorderRadius.circular(16),
                          border: Border.all(
                            color: conversation.id == selectedId
                                ? colors.primary
                                : colors.outlineVariant,
                          ),
                        ),
                        child: Column(
                          mainAxisSize: MainAxisSize.min,
                          children: [
                            Badge(
                              isLabelVisible: conversation.unreadCount > 0,
                              label: Text('${conversation.unreadCount}'),
                              child: AuthenticatedAvatar(
                                radius: 22,
                                baseUrl: baseUrl,
                                authToken: authToken,
                                imagePath: conversation.channelAvatarUrl,
                                fallbackText: conversation.displayChannelLabel,
                                cacheVersion: conversation
                                    .updatedAt
                                    .millisecondsSinceEpoch
                                    .toString(),
                              ),
                            ),
                            const SizedBox(height: 6),
                            Text(
                              _clientChannelName(conversation.kind),
                              maxLines: 1,
                              overflow: TextOverflow.ellipsis,
                              style: Theme.of(context).textTheme.labelMedium,
                            ),
                          ],
                        ),
                      ),
                    ),
                  ),
                ),
            ],
          ),
        ),
      ),
    );
  }
}

int _clientChannelOrder(String kind) => switch (kind) {
  'laboral' => 0,
  'fiscal' => 1,
  'private' => 2,
  _ => 3,
};

String _clientChannelName(String kind) => switch (kind) {
  'laboral' => 'Laboral',
  'fiscal' => 'Fiscal',
  'private' => 'Tu asesor',
  _ => 'Canal',
};

String _initials(String value) {
  final words = value
      .trim()
      .split(RegExp(r'\s+'))
      .where((word) => word.isNotEmpty);
  final initials = words.take(2).map((word) => word[0]).join().toUpperCase();
  return initials.isEmpty ? '?' : initials;
}

String _channelLabel(String kind) => switch (kind) {
  'laboral' => 'Laboral',
  'fiscal' => 'Contable / Fiscal',
  _ => 'Directo',
};

class _ClientGroupTile extends StatelessWidget {
  const _ClientGroupTile({
    required this.group,
    required this.selected,
    required this.onTap,
    this.onAccessChanged,
  });
  final ClientGroup group;
  final bool selected;
  final VoidCallback onTap;
  final ValueChanged<bool>? onAccessChanged;

  @override
  Widget build(BuildContext context) {
    final initials = group.displayName.isEmpty
        ? '?'
        : group.displayName
              .split(' ')
              .take(2)
              .map((w) => w.isEmpty ? '' : w[0])
              .join();
    return ListTile(
      key: Key('group-${group.companyCode}'),
      selected: selected,
      onTap: onTap,
      leading: CircleAvatar(child: Text(initials.toUpperCase())),
      title: Text(
        group.displayName,
        maxLines: 1,
        overflow: TextOverflow.ellipsis,
      ),
      subtitle: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(group.companyCode),
          Text(
            group.lastMessage?.deleted == true
                ? 'Mensaje eliminado'
                : group.lastMessage?.body ?? 'Sin mensajes',
            maxLines: 1,
            overflow: TextOverflow.ellipsis,
          ),
          Row(
            children: [
              for (final conv in group.conversations)
                Padding(
                  padding: const EdgeInsets.only(right: 4),
                  child: _ChannelChip(kind: conv.kind),
                ),
            ],
          ),
        ],
      ),
      isThreeLine: true,
      trailing: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          _ClientAccessBadge(
            status: group.clientAccessStatus,
            onAccessChanged: onAccessChanged,
          ),
          if (group.totalUnread > 0) ...[
            const SizedBox(width: 6),
            Badge(label: Text('${group.totalUnread}')),
          ],
        ],
      ),
    );
  }
}

class _ClientAccessBadge extends StatelessWidget {
  const _ClientAccessBadge({required this.status, this.onAccessChanged});

  final String status;
  final ValueChanged<bool>? onAccessChanged;

  @override
  Widget build(BuildContext context) {
    final (label, color) = switch (status) {
      'active' => ('Activo', Colors.green),
      'pending' => ('Invitado', Colors.orange),
      'disabled' => ('Desactivado', Colors.red),
      'invitation_expired' => ('Invitación caducada', Colors.deepOrange),
      _ => ('Sin invitar', Colors.grey),
    };
    final badge = Container(
      padding: const EdgeInsets.symmetric(horizontal: 7, vertical: 3),
      decoration: BoxDecoration(
        color: color.withValues(alpha: 0.12),
        borderRadius: BorderRadius.circular(12),
        border: Border.all(color: color.withValues(alpha: 0.45)),
      ),
      child: Text(
        label,
        style: TextStyle(
          color: color,
          fontSize: 10,
          fontWeight: FontWeight.w700,
        ),
      ),
    );
    final canChange =
        onAccessChanged != null &&
        {
          'active',
          'pending',
          'disabled',
          'invitation_expired',
        }.contains(status);
    if (!canChange) return badge;
    return PopupMenuButton<bool>(
      tooltip: 'Gestionar acceso del cliente',
      onSelected: onAccessChanged,
      itemBuilder: (_) => [
        PopupMenuItem<bool>(
          value: status == 'disabled',
          child: Text(
            status == 'disabled' ? 'Activar acceso' : 'Desactivar acceso',
          ),
        ),
      ],
      child: badge,
    );
  }
}

class _ChannelChip extends StatelessWidget {
  const _ChannelChip({required this.kind});
  final String kind;

  @override
  Widget build(BuildContext context) {
    if (kind == 'private') {
      return const CircleAvatar(
        radius: 10,
        child: Text(
          'AD',
          style: TextStyle(fontSize: 8, fontWeight: FontWeight.bold),
        ),
      );
    }
    return switch (kind) {
      'laboral' => const _LabelChip(label: 'LA', color: Colors.blue),
      'fiscal' => const _LabelChip(label: 'CF', color: Colors.green),
      _ => const _LabelChip(label: 'D', color: Colors.orange),
    };
  }
}

class _LabelChip extends StatelessWidget {
  const _LabelChip({required this.label, required this.color});
  final String label;
  final Color color;

  @override
  Widget build(BuildContext context) => Container(
    padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 2),
    decoration: BoxDecoration(
      color: color.withValues(alpha: 0.15),
      borderRadius: BorderRadius.circular(4),
      border: Border.all(color: color.withValues(alpha: 0.4)),
    ),
    child: Text(
      label,
      style: TextStyle(fontSize: 10, color: color, fontWeight: FontWeight.w700),
    ),
  );
}

class _AppDrawer extends StatelessWidget {
  const _AppDrawer({required this.profile});
  final UserProfile profile;

  void _navigate(BuildContext context, String route) {
    Navigator.of(context).pop();
    context.go(route);
  }

  @override
  Widget build(BuildContext context) => Drawer(
    child: ListView(
      children: [
        UserAccountsDrawerHeader(
          accountName: Text(profile.name),
          accountEmail: Text(profile.email),
          currentAccountPicture: _ProfileAvatar(profile: profile, radius: 32),
        ),
        ListTile(
          key: const Key('drawer-conversations'),
          leading: const Icon(Icons.forum_outlined),
          title: const Text('Conversaciones'),
          onTap: () => _navigate(context, '/'),
        ),
        if (profile.type == UserType.staff)
          ListTile(
            leading: const Icon(Icons.groups_outlined),
            title: const Text('Chats internos y grupos'),
            onTap: () => _navigate(context, '/groups'),
          ),
        if (profile.isAdmin)
          ListTile(
            leading: const Icon(Icons.campaign_outlined),
            title: const Text('Campañas'),
            onTap: () => _navigate(context, '/campaigns'),
          ),
        if (profile.isAdmin)
          ListTile(
            leading: const Icon(Icons.badge_outlined),
            title: const Text('Empleados'),
            onTap: () => _navigate(context, '/employees'),
          ),
        if (profile.isAdmin)
          ListTile(
            key: const Key('drawer-invite-client'),
            leading: const Icon(Icons.person_add_alt_1),
            title: const Text('Invitar cliente'),
            onTap: () => _navigate(context, '/invite-client'),
          ),
        ListTile(
          leading: const Icon(Icons.person_outline),
          title: const Text('Perfil'),
          onTap: () => _navigate(context, '/profile'),
        ),
        ListTile(
          leading: const Icon(Icons.info_outline),
          title: const Text('Acerca de Gestinem'),
          onTap: () => _navigate(context, '/about'),
        ),
      ],
    ),
  );
}

class _ProfileAvatar extends ConsumerWidget {
  const _ProfileAvatar({required this.profile, required this.radius});

  final UserProfile profile;
  final double radius;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final avatarUrl = profile.avatarUrl;
    return AuthenticatedAvatar(
      radius: radius,
      baseUrl: ref
          .read(apiClientProvider)
          .dio
          .options
          .baseUrl
          .replaceAll(RegExp(r'/api/v1/messaging/?$'), ''),
      authToken: ref.read(sessionProvider).valueOrNull?.token ?? '',
      imagePath: avatarUrl,
      fallbackText: _initials(profile.name),
      cacheVersion: avatarUrl.hashCode.toString(),
    );
  }
}
