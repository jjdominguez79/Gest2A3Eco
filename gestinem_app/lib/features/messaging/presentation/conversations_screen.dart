import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../../core/websocket/realtime_service.dart';
import '../../../core/notifications/notifications_service.dart';
import '../../auth/domain/user_profile.dart';
import '../../auth/presentation/auth_controller.dart';
import '../domain/conversation.dart';
import 'conversation_screen.dart';
import 'messaging_providers.dart';

final realtimeServiceProvider = Provider<RealtimeService>((ref) => RealtimeService());
final notificationsServiceProvider = Provider<NotificationsService>((ref) => NotificationsService());

class ConversationsScreen extends ConsumerStatefulWidget {
  const ConversationsScreen({super.key});

  @override
  ConsumerState<ConversationsScreen> createState() => _ConversationsScreenState();
}

class _ConversationsScreenState extends ConsumerState<ConversationsScreen> {
  final _search = TextEditingController();
  RealtimeService? _realtime;
  StreamSubscription<Map<String, dynamic>>? _events;
  String _channel = 'todos';
  String? _selected;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((_) => _connectRealtime());
  }

  void _connectRealtime() {
    final session = ref.read(sessionProvider).valueOrNull;
    if (session == null) return;
    _realtime = ref.read(realtimeServiceProvider);
    unawaited(ref.read(notificationsServiceProvider).initialize(session, ref.read(apiClientProvider)));
    _events = _realtime!.events.listen((event) {
      if (!mounted || event['type'] == 'ping') return;
      ref.invalidate(conversationsProvider);
      final id = event['conversation_id'] as String?;
      if (id != null) ref.invalidate(messagesProvider(id));
      final threadId = event['thread_id'] as String?;
      if (threadId != null) {
        ref.invalidate(internalThreadsProvider);
        ref.invalidate(internalMessagesProvider(threadId));
      }
    });
    unawaited(_realtime!.connect(session, ref.read(apiClientProvider)));
  }

  @override
  void dispose() {
    _search.dispose();
    _events?.cancel();
    _realtime?.close();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final profile = ref.watch(sessionProvider).valueOrNull!.profile;
    final conversations = ref.watch(conversationsProvider);
    final wide = MediaQuery.sizeOf(context).width >= 900;
    return Scaffold(
      appBar: AppBar(
        title: const Text('Gestinem'),
        actions: [
          IconButton(onPressed: () => ref.invalidate(conversationsProvider), icon: const Icon(Icons.refresh)),
          IconButton(onPressed: () => context.go('/profile'), icon: const Icon(Icons.account_circle_outlined)),
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
                    decoration: const InputDecoration(prefixIcon: Icon(Icons.search), hintText: 'Buscar por codigo o nombre'),
                    onChanged: (_) => setState(() {}),
                  ),
                ),
                SizedBox(
                  height: 46,
                  child: ListView(
                    scrollDirection: Axis.horizontal,
                    padding: const EdgeInsets.symmetric(horizontal: 10),
                    children: ['todos', 'laboral', 'fiscal', 'private'].map((channel) => Padding(
                      padding: const EdgeInsets.symmetric(horizontal: 3),
                      child: ChoiceChip(
                        label: Text(channel == 'todos' ? 'Todos' : channel),
                        selected: _channel == channel,
                        onSelected: (_) => setState(() => _channel = channel),
                      ),
                    )).toList(),
                  ),
                ),
                Expanded(
                  child: conversations.when(
                    loading: () => const Center(child: CircularProgressIndicator()),
                    error: (error, _) => Center(child: Text('No se pudieron cargar las conversaciones.\n$error', textAlign: TextAlign.center)),
                    data: (items) {
                      final query = _search.text.trim().toLowerCase();
                      final visible = items.where((item) {
                        final channelMatches = _channel == 'todos' || item.kind == _channel;
                        final searchMatches = query.isEmpty || item.companyCode.toLowerCase().contains(query) || item.companyName.toLowerCase().contains(query);
                        return channelMatches && searchMatches;
                      }).toList();
                      if (visible.isEmpty) return const Center(child: Text('No hay conversaciones'));
                      return RefreshIndicator(
                        onRefresh: () async => ref.invalidate(conversationsProvider),
                        child: ListView.builder(
                          key: const Key('conversation-list'),
                          itemCount: visible.length,
                          itemBuilder: (context, index) => _ConversationTile(
                            conversation: visible[index],
                            selected: visible[index].id == _selected,
                            onTap: () {
                              if (wide) {
                                setState(() => _selected = visible[index].id);
                              } else {
                                context.go('/conversation/${visible[index].id}');
                              }
                            },
                          ),
                        ),
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
                  ? const Center(child: Column(mainAxisSize: MainAxisSize.min, children: [Icon(Icons.forum_outlined, size: 58), SizedBox(height: 12), Text('Selecciona una conversacion')]))
                  : ConversationView(conversationId: _selected!),
            ),
          ],
        ],
      ),
    );
  }
}

class _ConversationTile extends StatelessWidget {
  const _ConversationTile({required this.conversation, required this.selected, required this.onTap});
  final Conversation conversation;
  final bool selected;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) => ListTile(
        key: Key('conversation-${conversation.id}'),
        selected: selected,
        onTap: onTap,
        leading: CircleAvatar(child: Text(conversation.title.isEmpty ? '?' : conversation.title[0].toUpperCase())),
        title: Text(conversation.title, maxLines: 1, overflow: TextOverflow.ellipsis),
        subtitle: Text('${conversation.companyCode} · ${conversation.kind}\n${conversation.lastMessage?.deleted == true ? 'Mensaje eliminado' : conversation.lastMessage?.body ?? 'Sin mensajes'}', maxLines: 2, overflow: TextOverflow.ellipsis),
        isThreeLine: true,
        trailing: conversation.unreadCount > 0
            ? Badge(label: Text('${conversation.unreadCount}'))
            : null,
      );
}

class _AppDrawer extends StatelessWidget {
  const _AppDrawer({required this.profile});
  final UserProfile profile;

  @override
  Widget build(BuildContext context) => Drawer(
        child: ListView(children: [
          UserAccountsDrawerHeader(
            accountName: Text(profile.name),
            accountEmail: Text(profile.email),
            currentAccountPicture: CircleAvatar(child: Text(profile.name.isEmpty ? '?' : profile.name[0])),
          ),
          ListTile(leading: const Icon(Icons.forum_outlined), title: const Text('Conversaciones'), onTap: () => context.go('/')),
          if (profile.type == UserType.staff)
            ListTile(leading: const Icon(Icons.groups_outlined), title: const Text('Chats internos y grupos'), onTap: () => context.go('/groups')),
          if (profile.isAdmin)
            ListTile(leading: const Icon(Icons.campaign_outlined), title: const Text('Campanas'), onTap: () => context.go('/campaigns')),
          ListTile(leading: const Icon(Icons.person_outline), title: const Text('Perfil'), onTap: () => context.go('/profile')),
        ]),
      );
}
