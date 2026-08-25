import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../../core/api/api_client.dart';
import '../../../core/notifications/notifications_service.dart';
import '../../../core/widgets/authenticated_avatar.dart';
import '../../auth/domain/user_profile.dart';
import '../../auth/presentation/auth_controller.dart';
import '../domain/conversation.dart';
import 'conversation_screen.dart';
import 'messaging_providers.dart';
import '../../../core/notifications/web_permission_banner.dart';

class ConversationsScreen extends ConsumerStatefulWidget {
  const ConversationsScreen({super.key});

  @override
  ConsumerState<ConversationsScreen> createState() =>
      _ConversationsScreenState();
}

class _ConversationsScreenState extends ConsumerState<ConversationsScreen>
    with WidgetsBindingObserver {
  final _search = TextEditingController();
  String? _selected;
  bool _selectedInternal = false;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addObserver(this);
    WidgetsBinding.instance.addPostFrameCallback(
      (_) => unawaited(_clearReadNotifications()),
    );
  }

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    if (state == AppLifecycleState.resumed) {
      _refreshMessaging();
      unawaited(_clearReadNotifications());
    }
  }

  Future<void> _clearReadNotifications() async {
    try {
      final service = ref.read(notificationsServiceProvider);
      final profile = ref.read(sessionProvider).valueOrNull?.profile;
      if (profile == null) return;
      final conversations = await ref.read(conversationsProvider.future);
      for (final item in conversations.where((item) => item.unreadCount == 0)) {
        await service.cancelTarget('conversation', item.id);
      }
      if (profile.type == UserType.staff) {
        final threads = await ref.read(internalThreadsProvider.future);
        for (final item in threads.where((item) => item.unreadCount == 0)) {
          await service.cancelTarget('internal_thread', item.id);
        }
      }
    } catch (_) {
      // La limpieza es oportunista; la bandeja sigue funcionando sin red.
    }
  }

  void _refreshMessaging([String? conversationId]) {
    ref.invalidate(conversationsProvider);
    ref.invalidate(unifiedConversationProvider);
    ref.invalidate(unifiedMessagesProvider);
    ref.invalidate(internalThreadsProvider);
    if (conversationId != null && conversationId.isNotEmpty) {
      ref.invalidate(messagesProvider(conversationId));
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

  Future<void> _showNewChat() async {
    try {
      final targets = await ref.read(conversationTargetsProvider.future);
      if (!mounted) return;
      final selected = await showModalBottomSheet<Conversation>(
        context: context,
        isScrollControlled: true,
        builder: (_) => _NewChatSheet(conversations: targets),
      );
      if (selected == null || !mounted) return;
      final started = await ref
          .read(messagingRepositoryProvider)
          .startConversation(selected.id);
      ref.invalidate(conversationTargetsProvider);
      ref.invalidate(conversationsProvider);
      if (mounted) _navigateToConversation(started.id);
    } catch (error) {
      if (mounted) {
        ScaffoldMessenger.of(
          context,
        ).showSnackBar(SnackBar(content: Text(apiErrorMessage(error))));
      }
    }
  }

  Future<void> _toggleRead(Conversation conversation) async {
    final profile = ref.read(sessionProvider).valueOrNull!.profile;
    final repo = ref.read(messagingRepositoryProvider);
    final hasUnread = conversation.unreadCount > 0;
    try {
      if (hasUnread) {
        await repo.markRead(profile, conversation.id);
      } else {
        await repo.markUnread(profile, conversation.id);
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

  @override
  Widget build(BuildContext context) {
    final profile = ref.watch(sessionProvider).valueOrNull!.profile;
    final conversations = ref.watch(conversationsProvider);
    if (profile.type == UserType.client) {
      return _buildClientScreen(profile, conversations);
    }
    final internalThreads = ref.watch(internalThreadsProvider);
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
          IconButton(
            key: const Key('new-chat-button'),
            tooltip: 'Nuevo chat',
            onPressed: _showNewChat,
            icon: const Icon(Icons.chat_outlined),
          ),
          if (profile.isAdmin)
            IconButton(
              key: const Key('clients-button'),
              tooltip: 'Clientes',
              onPressed: () => context.go('/clients'),
              icon: const Icon(Icons.people_alt_outlined),
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
      bottomNavigationBar: const WebNotificationPermissionBanner(),
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

                      if (profile.type == UserType.staff) {
                        return _StaffInbox(
                          query: query,
                          conversations: items,
                          threads: internalThreads,
                          selectedId: _selected,
                          selectedInternal: _selectedInternal,
                          baseUrl: apiBaseUrl,
                          authToken: authToken,
                          onConversation: _navigateToConversation,
                          onInternal: _navigateToInternal,
                          onToggleRead: _toggleRead,
                          onRefresh: () async => _refreshMessaging(),
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
    bottomNavigationBar: const WebNotificationPermissionBanner(),
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

class _StaffInbox extends StatelessWidget {
  const _StaffInbox({
    required this.query,
    required this.conversations,
    required this.threads,
    required this.selectedId,
    required this.selectedInternal,
    required this.baseUrl,
    required this.authToken,
    required this.onConversation,
    required this.onInternal,
    required this.onToggleRead,
    required this.onRefresh,
  });

  final String query;
  final List<Conversation> conversations;
  final AsyncValue<List<InternalThread>> threads;
  final String? selectedId;
  final bool selectedInternal;
  final String baseUrl;
  final String authToken;
  final ValueChanged<String> onConversation;
  final ValueChanged<String> onInternal;
  final ValueChanged<Conversation> onToggleRead;
  final Future<void> Function() onRefresh;

  bool _matches(String value) =>
      query.isEmpty || value.toLowerCase().contains(query);

  @override
  Widget build(BuildContext context) => threads.when(
    loading: () => const Center(child: CircularProgressIndicator()),
    error: (error, _) => Center(
      child: Text(
        'No se pudieron cargar los chats internos.\n$error',
        textAlign: TextAlign.center,
      ),
    ),
    data: (threadItems) {
      final groups =
          threadItems
              .where((item) => item.kind != 'direct' && _matches(item.title))
              .toList()
            ..sort(_compareThreads);
      final directThreads =
          threadItems
              .where((item) => item.kind == 'direct' && _matches(item.title))
              .toList()
            ..sort(_compareThreads);
      final clients = conversations.where((item) {
        return _matches(item.companyCode) || _matches(item.companyName);
      }).toList()..sort(_compareConversations);

      final children = <Widget>[
        const _InboxSectionHeader(
          key: Key('inbox-section-groups'),
          title: 'Grupos',
          icon: Icons.groups_outlined,
        ),
        if (groups.isEmpty)
          const _EmptySection('No hay grupos')
        else
          for (final thread in groups)
            _InternalThreadTile(
              thread: thread,
              selected: selectedInternal && selectedId == thread.id,
              baseUrl: baseUrl,
              authToken: authToken,
              onTap: () => onInternal(thread.id),
            ),
        const _InboxSectionHeader(
          key: Key('inbox-section-employees'),
          title: 'Empleados',
          icon: Icons.badge_outlined,
        ),
      ];

      if (directThreads.isNotEmpty) {
        children.addAll([
          for (final thread in directThreads)
            _InternalThreadTile(
              thread: thread,
              selected: selectedInternal && selectedId == thread.id,
              baseUrl: baseUrl,
              authToken: authToken,
              onTap: () => onInternal(thread.id),
            ),
        ]);
      } else {
        children.add(const _EmptySection('No hay empleados disponibles'));
      }

      children.add(
        const _InboxSectionHeader(
          key: Key('inbox-section-clients'),
          title: 'Clientes',
          icon: Icons.business_outlined,
        ),
      );
      if (clients.isEmpty) {
        children.add(const _EmptySection('No hay conversaciones de clientes'));
      } else {
        children.addAll([
          for (final conversation in clients)
            Dismissible(
              key: Key('swipe-conversation-${conversation.id}'),
              direction: DismissDirection.endToStart,
              confirmDismiss: (_) async {
                onToggleRead(conversation);
                return false;
              },
              background: Container(
                color: Colors.blue,
                alignment: Alignment.centerRight,
                padding: const EdgeInsets.symmetric(horizontal: 20),
                child: const Icon(
                  Icons.mark_chat_read_outlined,
                  color: Colors.white,
                ),
              ),
              child: _ClientConversationTile(
                conversation: conversation,
                selected: !selectedInternal && selectedId == conversation.id,
                onTap: () => onConversation(conversation.id),
              ),
            ),
        ]);
      }
      return RefreshIndicator(
        onRefresh: onRefresh,
        child: ListView(
          key: const Key('conversation-list'),
          physics: const AlwaysScrollableScrollPhysics(),
          children: children,
        ),
      );
    },
  );
}

int _compareThreads(InternalThread a, InternalThread b) {
  final unread = (b.unreadCount > 0 ? 1 : 0) - (a.unreadCount > 0 ? 1 : 0);
  return unread != 0
      ? unread
      : (b.updatedAt ?? DateTime(0)).compareTo(a.updatedAt ?? DateTime(0));
}

int _compareConversations(Conversation a, Conversation b) {
  final unread = (b.unreadCount > 0 ? 1 : 0) - (a.unreadCount > 0 ? 1 : 0);
  return unread != 0 ? unread : b.updatedAt.compareTo(a.updatedAt);
}

class _InboxSectionHeader extends StatelessWidget {
  const _InboxSectionHeader({
    super.key,
    required this.title,
    required this.icon,
  });
  final String title;
  final IconData icon;

  @override
  Widget build(BuildContext context) => ColoredBox(
    color: Theme.of(context).colorScheme.surfaceContainerLow,
    child: Padding(
      padding: const EdgeInsets.fromLTRB(14, 12, 14, 8),
      child: Row(
        children: [
          Icon(icon, size: 18),
          const SizedBox(width: 8),
          Text(title, style: Theme.of(context).textTheme.titleSmall),
        ],
      ),
    ),
  );
}

class _EmptySection extends StatelessWidget {
  const _EmptySection(this.label);
  final String label;

  @override
  Widget build(BuildContext context) => Padding(
    padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
    child: Text(
      label,
      style: Theme.of(context).textTheme.bodySmall?.copyWith(
        color: Theme.of(context).colorScheme.onSurfaceVariant,
      ),
    ),
  );
}

class _InternalThreadTile extends StatelessWidget {
  const _InternalThreadTile({
    required this.thread,
    required this.selected,
    required this.baseUrl,
    required this.authToken,
    required this.onTap,
  });
  final InternalThread thread;
  final bool selected;
  final String baseUrl;
  final String authToken;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) => ListTile(
    key: Key('internal-thread-${thread.id}'),
    selected: selected,
    onTap: onTap,
    leading: AuthenticatedAvatar(
      radius: 22,
      baseUrl: baseUrl,
      authToken: authToken,
      imagePath: thread.counterpartAvatarUrl,
      fallbackText: _initials(thread.title),
      cacheVersion: thread.id,
    ),
    title: Text(thread.title, maxLines: 1, overflow: TextOverflow.ellipsis),
    subtitle: Text(
      thread.lastMessage?.deleted == true
          ? 'Mensaje eliminado'
          : thread.lastMessage?.body ?? 'Sin mensajes',
      maxLines: 1,
      overflow: TextOverflow.ellipsis,
    ),
    trailing: _InboxTrailing(
      updatedAt: thread.updatedAt,
      unreadCount: thread.unreadCount,
    ),
  );
}

class _ClientConversationTile extends StatelessWidget {
  const _ClientConversationTile({
    required this.conversation,
    required this.selected,
    required this.onTap,
  });
  final Conversation conversation;
  final bool selected;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) => ListTile(
    key: Key('conversation-${conversation.id}'),
    selected: selected,
    onTap: onTap,
    leading: CircleAvatar(child: Text(_initials(conversation.title))),
    title: Text(
      conversation.title,
      maxLines: 1,
      overflow: TextOverflow.ellipsis,
    ),
    subtitle: Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(
          conversation.displayChannelLabel,
          style: Theme.of(context).textTheme.labelSmall?.copyWith(
            color: Theme.of(context).colorScheme.primary,
            fontWeight: FontWeight.w700,
          ),
        ),
        Text(
          conversation.lastMessage?.deleted == true
              ? 'Mensaje eliminado'
              : conversation.lastMessage?.body ?? 'Sin mensajes',
          maxLines: 1,
          overflow: TextOverflow.ellipsis,
        ),
      ],
    ),
    isThreeLine: true,
    trailing: _InboxTrailing(
      updatedAt: conversation.updatedAt,
      unreadCount: conversation.unreadCount,
    ),
  );
}

class _InboxTrailing extends StatelessWidget {
  const _InboxTrailing({required this.updatedAt, required this.unreadCount});
  final DateTime? updatedAt;
  final int unreadCount;

  @override
  Widget build(BuildContext context) => Column(
    mainAxisAlignment: MainAxisAlignment.center,
    crossAxisAlignment: CrossAxisAlignment.end,
    children: [
      Text(
        _conversationTime(updatedAt),
        style: Theme.of(context).textTheme.labelSmall,
      ),
      const SizedBox(height: 4),
      if (unreadCount > 0) Badge(label: Text('$unreadCount')),
    ],
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
                                cacheVersion:
                                    conversation.channelAvatarVersion.isNotEmpty
                                    ? conversation.channelAvatarVersion
                                    : conversation
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

String _conversationTime(DateTime? value) {
  if (value == null) return '';
  final now = DateTime.now();
  if (value.year == now.year &&
      value.month == now.month &&
      value.day == now.day) {
    return '${value.hour.toString().padLeft(2, '0')}:${value.minute.toString().padLeft(2, '0')}';
  }
  return '${value.day.toString().padLeft(2, '0')}/${value.month.toString().padLeft(2, '0')}';
}

class _NewChatSheet extends StatefulWidget {
  const _NewChatSheet({required this.conversations});

  final List<Conversation> conversations;

  @override
  State<_NewChatSheet> createState() => _NewChatSheetState();
}

class _NewChatSheetState extends State<_NewChatSheet> {
  final _search = TextEditingController();

  Conversation _defaultConversation(ClientGroup group) =>
      group.conversations.firstWhere(
        (conversation) => conversation.kind == 'private',
        orElse: () => group.conversations.first,
      );

  List<Conversation> _orderedConversations(ClientGroup group) =>
      [...group.conversations]..sort((a, b) {
        if (a.kind == 'private') return -1;
        if (b.kind == 'private') return 1;
        return _channelLabel(a.kind).compareTo(_channelLabel(b.kind));
      });

  @override
  void dispose() {
    _search.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final query = _search.text.trim().toLowerCase();
    final groups =
        groupConversationsByClient(widget.conversations)
            .where(
              (group) =>
                  query.isEmpty ||
                  group.companyCode.toLowerCase().contains(query) ||
                  group.displayName.toLowerCase().contains(query),
            )
            .toList()
          ..sort((a, b) => a.displayName.compareTo(b.displayName));
    return SafeArea(
      child: FractionallySizedBox(
        heightFactor: 0.82,
        child: Column(
          children: [
            Padding(
              padding: const EdgeInsets.fromLTRB(16, 18, 16, 8),
              child: Row(
                children: [
                  Expanded(
                    child: Text(
                      'Nuevo chat',
                      style: Theme.of(context).textTheme.titleLarge,
                    ),
                  ),
                  IconButton(
                    onPressed: () => Navigator.pop(context),
                    icon: const Icon(Icons.close),
                  ),
                ],
              ),
            ),
            Padding(
              padding: const EdgeInsets.fromLTRB(16, 0, 16, 12),
              child: TextField(
                key: const Key('new-chat-search'),
                controller: _search,
                autofocus: true,
                decoration: const InputDecoration(
                  prefixIcon: Icon(Icons.search),
                  hintText: 'Buscar cliente',
                ),
                onChanged: (_) => setState(() {}),
              ),
            ),
            Expanded(
              child: groups.isEmpty
                  ? const Center(
                      child: Text('No hay clientes invitados disponibles'),
                    )
                  : ListView(
                      key: const Key('new-chat-targets'),
                      children: [
                        for (final group in groups)
                          ListTile(
                            key: Key('new-chat-group-${group.companyCode}'),
                            leading: CircleAvatar(
                              child: Text(_initials(group.displayName)),
                            ),
                            title: Text(group.displayName),
                            subtitle: Text(
                              '${group.companyCode} · ${_channelLabel(_defaultConversation(group).kind)}',
                            ),
                            onTap: () => Navigator.pop(
                              context,
                              _defaultConversation(group),
                            ),
                            trailing: group.conversations.length > 1
                                ? PopupMenuButton<Conversation>(
                                    tooltip: 'Elegir otro canal',
                                    onSelected: (conversation) =>
                                        Navigator.pop(context, conversation),
                                    itemBuilder: (_) => [
                                      for (final conversation
                                          in _orderedConversations(group))
                                        PopupMenuItem(
                                          key: Key(
                                            'new-chat-${conversation.id}',
                                          ),
                                          value: conversation,
                                          child: Row(
                                            children: [
                                              _ChannelChip(
                                                kind: conversation.kind,
                                              ),
                                              const SizedBox(width: 10),
                                              Text(
                                                _channelLabel(
                                                  conversation.kind,
                                                ),
                                              ),
                                            ],
                                          ),
                                        ),
                                    ],
                                    icon: const Icon(Icons.more_vert),
                                  )
                                : const Icon(Icons.chat_outlined),
                          ),
                      ],
                    ),
            ),
          ],
        ),
      ),
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
        if (profile.isAdmin)
          ListTile(
            leading: const Icon(Icons.groups_outlined),
            title: const Text('Gestionar grupos internos'),
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
            key: const Key('drawer-clients'),
            leading: const Icon(Icons.people_alt_outlined),
            title: const Text('Clientes'),
            onTap: () => _navigate(context, '/clients'),
          ),
        if (profile.type == UserType.client) ...[
          ListTile(
            leading: const Icon(Icons.business_outlined),
            title: const Text('Mi empresa'),
            onTap: () => _navigate(context, '/company-profile'),
          ),
          ListTile(
            leading: const Icon(Icons.folder_outlined),
            title: const Text('Mis documentos'),
            onTap: () => _navigate(context, '/documents'),
          ),
        ],
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
