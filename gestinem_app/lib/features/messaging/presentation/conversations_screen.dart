import 'dart:async';

import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:url_launcher/url_launcher.dart';

import '../../../core/api/api_client.dart';
import '../../../core/config/app_config.dart';
import '../../../core/notifications/notifications_service.dart';
import '../../../core/widgets/authenticated_avatar.dart';
import '../../auth/domain/user_profile.dart';
import '../../auth/presentation/auth_controller.dart';
import '../../company_profile/presentation/company_profile_providers.dart';
import '../domain/conversation.dart';
import 'conversation_screen.dart';
import 'messaging_providers.dart';
import '../../../core/notifications/web_permission_banner.dart';
import '../../platform/features_provider.dart';

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
      if (profile.type == UserType.staff) {
        final inbox = await ref.read(staffInboxProvider.future);
        for (final item in inbox.conversations.where(
          (item) => item.unreadCount == 0,
        )) {
          await service.cancelTarget('conversation', item.id);
        }
        for (final item in inbox.threads.where(
          (item) => item.unreadCount == 0,
        )) {
          await service.cancelTarget('internal_thread', item.id);
        }
        return;
      }
      final conversations = await ref.read(conversationsProvider.future);
      for (final item in conversations.where((item) => item.unreadCount == 0)) {
        await service.cancelTarget('conversation', item.id);
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
    ref.invalidate(staffInboxProvider);
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
      ref.invalidate(staffInboxProvider);
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
      ref.invalidate(staffInboxProvider);
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
    final profile = ref.watch(sessionProvider).valueOrNull?.profile;
    if (profile == null) return const SizedBox.shrink();
    if (profile.type == UserType.client) {
      return _buildClientScreen(profile, ref.watch(conversationsProvider));
    }
    final inbox = ref.watch(staffInboxProvider);
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
        title: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            const Text('Chats'),
            Text(
              profile.name,
              maxLines: 1,
              overflow: TextOverflow.ellipsis,
              style: Theme.of(context).textTheme.bodySmall,
            ),
          ],
        ),
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
            onPressed: _refreshMessaging,
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
      bottomNavigationBar: kIsWeb
          ? const WebNotificationPermissionBanner()
          : null,
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
                      hintText: 'Buscar chats',
                    ),
                    onChanged: (_) => setState(() {}),
                  ),
                ),
                Expanded(
                  child: inbox.when(
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
                      return _StaffInbox(
                        query: query,
                        conversations: items.conversations,
                        threads: AsyncData(items.threads),
                        labels: items.labels,
                        currentUserId: profile.id,
                        selectedId: _selected,
                        selectedInternal: _selectedInternal,
                        baseUrl: apiBaseUrl,
                        authToken: authToken,
                        onConversation: _navigateToConversation,
                        onInternal: _navigateToInternal,
                        onToggleRead: _toggleRead,
                        onRefresh: () async => _refreshMessaging(),
                      );
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
    drawer: _AppDrawer(profile: profile),
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
    ),
    bottomNavigationBar: kIsWeb
        ? const WebNotificationPermissionBanner()
        : null,
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

enum _InboxFilter { all, unread, favorites, groups }

enum _InboxAction { favorite }

class _InboxEntry {
  const _InboxEntry.conversation(this.conversation) : thread = null;
  const _InboxEntry.thread(this.thread) : conversation = null;

  final Conversation? conversation;
  final InternalThread? thread;

  String get id => conversation?.id ?? thread!.id;
  String get targetType =>
      conversation != null ? 'conversation' : 'internal_thread';
  String get title => conversation?.title ?? thread!.title;
  String get searchText => [
    title,
    conversation?.companyCode ?? '',
    ...labels.map((label) => label.name),
  ].join(' ').toLowerCase();
  int get unreadCount => conversation?.unreadCount ?? thread!.unreadCount;
  DateTime get updatedAt =>
      conversation?.lastMessage?.createdAt ??
      conversation?.startedAt ??
      conversation?.updatedAt ??
      thread?.lastMessage?.createdAt ??
      thread?.updatedAt ??
      DateTime(0);
  bool get isGroup => thread != null && thread!.kind != 'direct';
  bool get isFavorite => conversation?.isFavorite ?? thread!.isFavorite;
  List<ChatLabel> get labels => conversation?.labels ?? thread!.labels;
}

class _StaffInbox extends ConsumerStatefulWidget {
  const _StaffInbox({
    required this.query,
    required this.conversations,
    required this.threads,
    required this.labels,
    required this.currentUserId,
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
  final List<ChatLabel> labels;
  final String currentUserId;
  final String? selectedId;
  final bool selectedInternal;
  final String baseUrl;
  final String authToken;
  final ValueChanged<String> onConversation;
  final ValueChanged<String> onInternal;
  final ValueChanged<Conversation> onToggleRead;
  final Future<void> Function() onRefresh;

  @override
  ConsumerState<_StaffInbox> createState() => _StaffInboxState();
}

class _StaffInboxState extends ConsumerState<_StaffInbox> {
  _InboxFilter _filter = _InboxFilter.all;
  String? _labelId;

  bool _matches(String value) =>
      widget.query.isEmpty || value.toLowerCase().contains(widget.query);

  void _selectFilter(_InboxFilter value) {
    setState(() {
      _filter = value;
      _labelId = null;
    });
  }

  Future<void> _toggleFavorite(_InboxEntry entry) async {
    try {
      await ref
          .read(messagingRepositoryProvider)
          .setChatFavorite(entry.targetType, entry.id, !entry.isFavorite);
      _refreshEntry(entry);
    } catch (error) {
      _showError(error);
    }
  }

  Future<void> _chooseLabelFilter(List<ChatLabel> labels) async {
    final selected = await showModalBottomSheet<String>(
      context: context,
      builder: (context) => SafeArea(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            const ListTile(
              leading: Icon(Icons.label_outline),
              title: Text('Filtrar por etiqueta'),
            ),
            ListTile(
              key: const Key('filter-label-all'),
              leading: const Icon(Icons.clear_all),
              title: const Text('Todas las etiquetas'),
              onTap: () => Navigator.pop(context, '__all__'),
            ),
            for (final label in labels)
              ListTile(
                key: Key('filter-label-${label.id}'),
                leading: Icon(Icons.label, color: _chatLabelColor(label.color)),
                title: Text(label.name),
                trailing: _labelId == label.id ? const Icon(Icons.check) : null,
                onTap: () => Navigator.pop(context, label.id),
              ),
          ],
        ),
      ),
    );
    if (!mounted || selected == null) return;
    setState(() {
      _filter = _InboxFilter.all;
      _labelId = selected == '__all__' ? null : selected;
    });
  }

  void _refreshEntry(_InboxEntry entry) {
    ref.invalidate(staffInboxProvider);
    if (entry.conversation != null) {
      ref.invalidate(conversationsProvider);
    } else {
      ref.invalidate(internalThreadsProvider);
    }
  }

  void _showError(Object error) {
    if (!mounted) return;
    ScaffoldMessenger.of(
      context,
    ).showSnackBar(SnackBar(content: Text(apiErrorMessage(error))));
  }

  @override
  Widget build(BuildContext context) => widget.threads.when(
    loading: () => const Center(child: CircularProgressIndicator()),
    error: (error, _) => Center(
      child: Text(
        'No se pudieron cargar los chats internos.\n$error',
        textAlign: TextAlign.center,
      ),
    ),
    data: (threadItems) {
      final normalizedUserId = widget.currentUserId.trim().toLowerCase();
      final entries =
          <_InboxEntry>[
              for (final thread in threadItems)
                if (thread.active &&
                    (thread.kind != 'direct' ||
                        (thread.counterpartActive &&
                            thread.counterpartId.trim().toLowerCase() !=
                                normalizedUserId)))
                  _InboxEntry.thread(thread),
              for (final conversation in widget.conversations)
                _InboxEntry.conversation(conversation),
            ].where((entry) {
              if (!_matches(entry.searchText)) return false;
              if (_labelId != null &&
                  !entry.labels.any((label) => label.id == _labelId)) {
                return false;
              }
              return switch (_filter) {
                _InboxFilter.all => true,
                _InboxFilter.unread => entry.unreadCount > 0,
                _InboxFilter.favorites => entry.isFavorite,
                _InboxFilter.groups => entry.isGroup,
              };
            }).toList()
            ..sort((a, b) => b.updatedAt.compareTo(a.updatedAt));

      final labels = widget.labels;
      final bottomPadding = MediaQuery.viewPaddingOf(context).bottom;
      return Column(
        children: [
          SingleChildScrollView(
            scrollDirection: Axis.horizontal,
            padding: const EdgeInsets.fromLTRB(12, 4, 12, 8),
            child: Row(
              children: [
                ChoiceChip(
                  key: const Key('inbox-filter-all'),
                  label: const Text('Todos'),
                  selected: _filter == _InboxFilter.all && _labelId == null,
                  onSelected: (_) => _selectFilter(_InboxFilter.all),
                ),
                const SizedBox(width: 8),
                ChoiceChip(
                  key: const Key('inbox-filter-unread'),
                  label: const Text('No leídos'),
                  selected: _filter == _InboxFilter.unread,
                  onSelected: (_) => _selectFilter(_InboxFilter.unread),
                ),
                const SizedBox(width: 8),
                ChoiceChip(
                  key: const Key('inbox-filter-favorites'),
                  label: const Text('Favoritos'),
                  selected: _filter == _InboxFilter.favorites,
                  onSelected: (_) => _selectFilter(_InboxFilter.favorites),
                ),
                const SizedBox(width: 8),
                ChoiceChip(
                  key: const Key('inbox-filter-groups'),
                  label: const Text('Grupos'),
                  selected: _filter == _InboxFilter.groups,
                  onSelected: (_) => _selectFilter(_InboxFilter.groups),
                ),
                const SizedBox(width: 8),
                FilterChip(
                  key: const Key('inbox-filter-labels'),
                  avatar: const Icon(Icons.label_outline, size: 18),
                  label: Text(
                    labels
                            .where((label) => label.id == _labelId)
                            .firstOrNull
                            ?.name ??
                        'Etiquetas',
                  ),
                  selected: _labelId != null,
                  onSelected: (_) => _chooseLabelFilter(labels),
                ),
              ],
            ),
          ),
          const Divider(height: 1),
          Expanded(
            child: RefreshIndicator(
              onRefresh: () async {
                ref.invalidate(chatLabelsProvider);
                await widget.onRefresh();
              },
              child: ListView.builder(
                key: const Key('inbox-unified-list'),
                physics: const AlwaysScrollableScrollPhysics(),
                padding: EdgeInsets.only(bottom: bottomPadding),
                itemCount: entries.isEmpty ? 1 : entries.length,
                itemBuilder: (context, index) {
                  if (entries.isEmpty) {
                    return const _EmptySection(
                      'No hay chats que coincidan con el filtro',
                    );
                  }
                  final entry = entries[index];
                  final conversation = entry.conversation;
                  if (conversation != null) {
                    return Dismissible(
                      key: Key('swipe-conversation-${conversation.id}'),
                      direction: DismissDirection.endToStart,
                      confirmDismiss: (_) async {
                        widget.onToggleRead(conversation);
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
                        selected:
                            !widget.selectedInternal &&
                            widget.selectedId == conversation.id,
                        baseUrl: widget.baseUrl,
                        authToken: widget.authToken,
                        onTap: () => widget.onConversation(conversation.id),
                        onFavorite: () => _toggleFavorite(entry),
                      ),
                    );
                  }
                  final thread = entry.thread!;
                  return _InternalThreadTile(
                    thread: thread,
                    selected:
                        widget.selectedInternal &&
                        widget.selectedId == thread.id,
                    baseUrl: widget.baseUrl,
                    authToken: widget.authToken,
                    onTap: () => widget.onInternal(thread.id),
                    onFavorite: () => _toggleFavorite(entry),
                  );
                },
              ),
            ),
          ),
        ],
      );
    },
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
    required this.onFavorite,
  });
  final InternalThread thread;
  final bool selected;
  final String baseUrl;
  final String authToken;
  final VoidCallback onTap;
  final VoidCallback onFavorite;

  @override
  Widget build(BuildContext context) => ListTile(
    key: Key('internal-thread-${thread.id}'),
    selected: selected,
    onTap: onTap,
    leading: Stack(
      clipBehavior: Clip.none,
      children: [
        AuthenticatedAvatar(
          radius: 22,
          baseUrl: baseUrl,
          authToken: authToken,
          imagePath: thread.counterpartAvatarUrl,
          fallbackText: _initials(thread.title),
          cacheVersion: thread.counterpartAvatarVersion,
        ),
        if (thread.kind == 'direct')
          Positioned(
            right: -1,
            bottom: -1,
            child: Container(
              width: 13,
              height: 13,
              decoration: BoxDecoration(
                shape: BoxShape.circle,
                color: thread.counterpartOnline ? Colors.green : Colors.grey,
                border: Border.all(
                  color: Theme.of(context).colorScheme.surface,
                  width: 2,
                ),
              ),
            ),
          ),
      ],
    ),
    title: _InboxTitle(
      title: thread.title,
      favorite: thread.isFavorite,
      labels: thread.labels,
    ),
    subtitle: Text(
      _labeledPreview(
        thread.labels,
        !thread.active
            ? 'Histórico · solo lectura'
            : thread.lastMessage?.deleted == true
            ? 'Mensaje eliminado'
            : thread.lastMessage?.body ?? 'Sin mensajes',
      ),
      maxLines: 1,
      overflow: TextOverflow.ellipsis,
    ),
    trailing: _InboxTrailing(
      updatedAt: thread.updatedAt,
      unreadCount: thread.unreadCount,
      favorite: thread.isFavorite,
      onFavorite: onFavorite,
    ),
  );
}

class _ClientConversationTile extends StatelessWidget {
  const _ClientConversationTile({
    required this.conversation,
    required this.selected,
    required this.baseUrl,
    required this.authToken,
    required this.onTap,
    required this.onFavorite,
  });
  final Conversation conversation;
  final bool selected;
  final String baseUrl;
  final String authToken;
  final VoidCallback onTap;
  final VoidCallback onFavorite;

  @override
  Widget build(BuildContext context) => ListTile(
    key: Key('conversation-${conversation.id}'),
    selected: selected,
    onTap: onTap,
    leading: AuthenticatedAvatar(
      radius: 22,
      baseUrl: baseUrl,
      authToken: authToken,
      imagePath: conversation.channelAvatarUrl,
      fallbackText: _initials(conversation.title),
      cacheVersion: conversation.channelAvatarVersion,
    ),
    title: _InboxTitle(
      title: conversation.title,
      favorite: conversation.isFavorite,
      labels: conversation.labels,
    ),
    subtitle: Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(
          conversation.displayChannelKind,
          style: Theme.of(context).textTheme.labelSmall?.copyWith(
            color: Theme.of(context).colorScheme.primary,
            fontWeight: FontWeight.w700,
          ),
        ),
        Text(
          _labeledPreview(
            conversation.labels,
            conversation.lastMessage?.deleted == true
                ? 'Mensaje eliminado'
                : conversation.lastMessage?.body ?? 'Sin mensajes',
          ),
          maxLines: 1,
          overflow: TextOverflow.ellipsis,
        ),
      ],
    ),
    isThreeLine: true,
    trailing: _InboxTrailing(
      updatedAt: conversation.updatedAt,
      unreadCount: conversation.unreadCount,
      favorite: conversation.isFavorite,
      onFavorite: onFavorite,
    ),
  );
}

class _InboxTitle extends StatelessWidget {
  const _InboxTitle({
    required this.title,
    required this.favorite,
    required this.labels,
  });

  final String title;
  final bool favorite;
  final List<ChatLabel> labels;

  @override
  Widget build(BuildContext context) => Row(
    children: [
      Expanded(
        child: Text(title, maxLines: 1, overflow: TextOverflow.ellipsis),
      ),
      if (favorite) ...[
        const SizedBox(width: 4),
        Icon(
          Icons.star,
          size: 16,
          color: Theme.of(context).colorScheme.primary,
        ),
      ],
      for (final label in labels.take(2)) ...[
        const SizedBox(width: 4),
        Tooltip(
          message: label.name,
          child: Icon(
            Icons.label,
            size: 15,
            color: _chatLabelColor(label.color),
          ),
        ),
      ],
    ],
  );
}

class _InboxTrailing extends StatelessWidget {
  const _InboxTrailing({
    required this.updatedAt,
    required this.unreadCount,
    required this.favorite,
    required this.onFavorite,
  });
  final DateTime? updatedAt;
  final int unreadCount;
  final bool favorite;
  final VoidCallback onFavorite;

  @override
  Widget build(BuildContext context) => Row(
    mainAxisSize: MainAxisSize.min,
    children: [
      Column(
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
      ),
      PopupMenuButton<_InboxAction>(
        tooltip: 'Organizar chat',
        padding: EdgeInsets.zero,
        icon: const Icon(Icons.more_vert, size: 20),
        onSelected: (_) => onFavorite(),
        itemBuilder: (context) => [
          PopupMenuItem(
            value: _InboxAction.favorite,
            child: ListTile(
              contentPadding: EdgeInsets.zero,
              leading: Icon(favorite ? Icons.star : Icons.star_outline),
              title: Text(
                favorite ? 'Quitar de favoritos' : 'Añadir a favoritos',
              ),
            ),
          ),
        ],
      ),
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
  'general' => 0,
  'private' => 1,
  _ => 2,
};

String _clientChannelName(String kind) => switch (kind) {
  'general' => 'Canal general',
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
  'general' => 'Canal general',
  'private' => 'Tu asesor',
  _ => 'Canal',
};

String _labeledPreview(List<ChatLabel> labels, String message) {
  if (labels.isEmpty) return message;
  return '${labels.map((label) => label.name).take(2).join(' · ')} · $message';
}

Color _chatLabelColor(String value) {
  final normalized = value.replaceFirst('#', '');
  final parsed = int.tryParse(normalized, radix: 16);
  return parsed == null ? const Color(0xFF6750A4) : Color(0xFF000000 | parsed);
}

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
        (conversation) => conversation.kind == 'general',
        orElse: () => group.conversations.first,
      );

  List<Conversation> _orderedConversations(ClientGroup group) =>
      [...group.conversations]..sort((a, b) {
        if (a.kind == 'general') return -1;
        if (b.kind == 'general') return 1;
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
      'general' => const _LabelChip(label: 'CG', color: Colors.green),
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

class _AppDrawer extends ConsumerWidget {
  const _AppDrawer({required this.profile});
  final UserProfile profile;

  void _navigate(BuildContext context, String route) {
    Navigator.of(context).pop();
    if (route == '/') {
      context.go(route);
    } else {
      // Conservar el inicio para poder volver desde las opciones del menu.
      context.push(route);
    }
  }

  Future<void> _cerrarSesion(BuildContext context, WidgetRef ref) async {
    final sesion = ref.read(sessionProvider.notifier);
    Navigator.of(context).pop();
    try {
      await sesion.logout();
    } catch (error) {
      if (context.mounted) {
        ScaffoldMessenger.of(
          context,
        ).showSnackBar(SnackBar(content: Text(apiErrorMessage(error))));
      }
    }
  }

  Future<void> _abrirManual(BuildContext context) async {
    Navigator.of(context).pop();
    final opened = await launchUrl(
      Uri.parse('${appConfig.apiBaseUrl}/public/client-manual'),
      mode: LaunchMode.externalApplication,
    );
    if (!opened && context.mounted) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('No se pudo abrir el manual.')),
      );
    }
  }

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final featuresAsync = profile.type == UserType.client
        ? ref.watch(platformFeaturesProvider)
        : null;
    final features = featuresAsync?.valueOrNull ?? const PlatformFeatures();

    return Drawer(
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
              key: const Key('drawer-groups'),
              leading: const Icon(Icons.groups_outlined),
              title: Text(
                profile.isAdmin
                    ? 'Grupos y listas de clientes'
                    : 'Grupos internos',
              ),
              onTap: () => _navigate(context, '/groups'),
            ),
          if (profile.isAdmin)
            ListTile(
              key: const Key('drawer-dgt'),
              leading: const Icon(Icons.directions_car_outlined),
              title: const Text('Trámites DGT'),
              onTap: () => _navigate(context, '/dgt'),
            ),
          if (profile.isAdmin)
            ListTile(
              key: const Key('drawer-broadcasts'),
              leading: const Icon(Icons.campaign_outlined),
              title: const Text('Difusiones'),
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
          if (profile.isAdmin)
            ListTile(
              key: const Key('drawer-admin-subvenciones'),
              leading: const Icon(Icons.savings_outlined),
              title: const Text('Base de datos de ayudas'),
              onTap: () => _navigate(context, '/admin/subvenciones'),
            ),
          if (profile.isAdmin)
            ListTile(
              key: const Key('drawer-invitation-content'),
              leading: const Icon(Icons.forward_to_inbox_outlined),
              title: const Text('Invitación y manual'),
              onTap: () => _navigate(context, '/invitation-content'),
            ),
          if (profile.type == UserType.client) ...[
            ListTile(
              key: const Key('drawer-documentation'),
              leading: const Icon(Icons.folder_outlined),
              title: const Text('Documentaci\u00f3n'),
              onTap: () => _navigate(context, '/documentation'),
            ),
            if (features.invoicing)
              ListTile(
                key: const Key('drawer-invoicing'),
                leading: const Icon(Icons.receipt_long_outlined),
                title: const Text('Facturaci\u00f3n'),
                onTap: () => _navigate(context, '/invoicing'),
              ),
            if (features.subsidies)
              ListTile(
                key: const Key('drawer-subvenciones'),
                leading: const Icon(Icons.savings_outlined),
                title: const Text('Ayudas y subvenciones'),
                onTap: () => _navigate(context, '/subvenciones'),
              ),
            ListTile(
              key: const Key('drawer-profile'),
              leading: const Icon(Icons.account_circle_outlined),
              title: const Text('Mi área'),
              onTap: () => _navigate(context, '/profile'),
            ),
          ],
          if (profile.type == UserType.staff)
            ListTile(
              leading: const Icon(Icons.person_outline),
              title: const Text('Perfil'),
              onTap: () => _navigate(context, '/profile'),
            ),
          ListTile(
            key: const Key('drawer-user-manual'),
            leading: const Icon(Icons.menu_book_outlined),
            title: const Text('Manual de Gestinem'),
            trailing: const Icon(Icons.open_in_new),
            onTap: () => _abrirManual(context),
          ),
          ListTile(
            leading: const Icon(Icons.info_outline),
            title: const Text('Acerca de Gestinem'),
            onTap: () => _navigate(context, '/about'),
          ),
          const Divider(),
          ListTile(
            key: const Key('drawer-logout'),
            leading: const Icon(Icons.logout),
            title: const Text('Cerrar sesi\u00f3n'),
            onTap: () => _cerrarSesion(context, ref),
          ),
        ],
      ),
    );
  }
}

class _ProfileAvatar extends ConsumerWidget {
  const _ProfileAvatar({required this.profile, required this.radius});

  final UserProfile profile;
  final double radius;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    if (profile.type == UserType.client) {
      final company = ref.watch(companyProfileProvider).valueOrNull;
      if (company?.logoUrl?.isNotEmpty == true) {
        return AuthenticatedAvatar(
          radius: radius,
          baseUrl: ref
              .read(apiClientProvider)
              .dio
              .options
              .baseUrl
              .replaceAll(RegExp(r'/api/v1/messaging/?$'), ''),
          authToken: ref.read(sessionProvider).valueOrNull?.token ?? '',
          imagePath: company!.logoUrl!,
          fallbackText: company.name.isEmpty ? 'E' : company.name[0],
          cacheVersion: company.profileSyncedAt ?? company.name,
        );
      }
      return CircleAvatar(
        radius: radius,
        backgroundColor: Theme.of(context).colorScheme.primaryContainer,
        child: Icon(
          Icons.business,
          size: radius,
          color: Theme.of(context).colorScheme.onPrimaryContainer,
        ),
      );
    }
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
