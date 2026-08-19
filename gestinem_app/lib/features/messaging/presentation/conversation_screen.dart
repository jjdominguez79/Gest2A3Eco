import 'package:file_picker/file_picker.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../../core/api/api_client.dart';
import '../../../core/widgets/authenticated_avatar.dart';
import '../../auth/presentation/auth_controller.dart';
import '../domain/conversation.dart';
import '../domain/message.dart';
import 'message_bubble.dart';
import 'messaging_providers.dart';

class ConversationScreen extends ConsumerWidget {
  const ConversationScreen({
    super.key,
    required this.conversationId,
    this.internal = false,
  });
  final String conversationId;
  final bool internal;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final thread = internal
        ? _findThread(
            ref.watch(internalThreadsProvider).valueOrNull,
            conversationId,
          )
        : null;
    return Scaffold(
      appBar: AppBar(
        leading: IconButton(
          onPressed: () => context.go(internal ? '/groups' : '/'),
          icon: const Icon(Icons.arrow_back),
        ),
        title: internal
            ? _InternalThreadIdentity(thread: thread)
            : const Text('Conversación'),
      ),
      body: ConversationView(
        conversationId: conversationId,
        internal: internal,
      ),
    );
  }
}

class ConversationView extends ConsumerStatefulWidget {
  const ConversationView({
    super.key,
    required this.conversationId,
    this.internal = false,
    this.showInternalHeader = false,
  });
  final String conversationId;
  final bool internal;
  final bool showInternalHeader;

  @override
  ConsumerState<ConversationView> createState() => _ConversationViewState();
}

class _ConversationViewState extends ConsumerState<ConversationView> {
  final _body = TextEditingController();
  final _scroll = ScrollController();
  List<PlatformFile> _files = [];
  Message? _replyingTo;
  bool _sending = false;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((_) => _markRead());
  }

  @override
  void dispose() {
    _body.dispose();
    _scroll.dispose();
    super.dispose();
  }

  Future<void> _markRead() async {
    if (widget.internal) return;
    final profile = ref.read(sessionProvider).valueOrNull!.profile;
    await ref
        .read(messagingRepositoryProvider)
        .markRead(profile, widget.conversationId);
    ref.invalidate(conversationsProvider);
  }

  Future<void> _pickFiles() async {
    final result = await FilePicker.pickFiles(
      allowedExtensions: [
        'pdf',
        'png',
        'jpg',
        'jpeg',
        'gif',
        'tif',
        'tiff',
        'txt',
        'xml',
        'csv',
        'xls',
        'xlsx',
        'doc',
        'docx',
        'zip',
      ],
      type: FileType.custom,
    );
    if (result.isNotEmpty) setState(() => _files = result);
  }

  Future<void> _send() async {
    if (_body.text.trim().isEmpty && _files.isEmpty || _sending) return;
    setState(() => _sending = true);
    try {
      final repository = ref.read(messagingRepositoryProvider);
      if (widget.internal) {
        await repository.sendInternal(
          widget.conversationId,
          _body.text,
          replyToMessageId: _replyingTo?.id,
        );
        ref.invalidate(internalMessagesProvider(widget.conversationId));
      } else {
        final profile = ref.read(sessionProvider).valueOrNull!.profile;
        await repository.send(
          profile,
          widget.conversationId,
          _body.text,
          _files,
          replyToMessageId: _replyingTo?.id,
        );
        ref.invalidate(messagesProvider(widget.conversationId));
        ref.invalidate(conversationsProvider);
      }
      _body.clear();
      setState(() {
        _files = [];
        _replyingTo = null;
      });
    } catch (error) {
      if (mounted) {
        ScaffoldMessenger.of(
          context,
        ).showSnackBar(SnackBar(content: Text(apiErrorMessage(error))));
      }
    } finally {
      if (mounted) setState(() => _sending = false);
    }
  }

  void _scrollToMessage(List<Message> messages, String id) {
    final index = messages.indexWhere((message) => message.id == id);
    if (index >= 0 && _scroll.hasClients) {
      _scroll.animateTo(
        index * 96.0,
        duration: const Duration(milliseconds: 350),
        curve: Curves.easeOut,
      );
    }
  }

  Future<void> _download(Attachment attachment) async {
    try {
      final profile = ref.read(sessionProvider).valueOrNull!.profile;
      final bytes = await ref
          .read(messagingRepositoryProvider)
          .download(profile, attachment);
      await FilePicker.saveFile(
        fileName: attachment.name,
        bytes: bytes,
        mimeType: attachment.contentType,
      );
    } catch (error) {
      if (mounted) {
        ScaffoldMessenger.of(
          context,
        ).showSnackBar(SnackBar(content: Text(apiErrorMessage(error))));
      }
    }
  }

  Future<void> _messageActions(Message message, bool mine) async {
    final profile = ref.read(sessionProvider).valueOrNull!.profile;
    final action = await showModalBottomSheet<String>(
      context: context,
      builder: (context) => SafeArea(
        child: Wrap(
          children: [
            ListTile(
              leading: const Icon(Icons.reply),
              title: const Text('Responder'),
              onTap: () => Navigator.pop(context, 'reply'),
            ),
            if (mine || profile.isAdmin)
              ListTile(
                leading: const Icon(Icons.delete_outline),
                title: const Text('Eliminar mensaje'),
                textColor: Theme.of(context).colorScheme.error,
                iconColor: Theme.of(context).colorScheme.error,
                onTap: () => Navigator.pop(context, 'delete'),
              ),
          ],
        ),
      ),
    );
    if (!mounted) return;
    if (action == 'reply') {
      setState(() => _replyingTo = message);
    } else if (action == 'delete') {
      final confirmed = await showDialog<bool>(
        context: context,
        builder: (context) => AlertDialog(
          title: const Text('Eliminar mensaje'),
          content: const Text(
            'El contenido se sustituirá por "Mensaje eliminado".',
          ),
          actions: [
            TextButton(
              onPressed: () => Navigator.pop(context, false),
              child: const Text('Cancelar'),
            ),
            FilledButton(
              onPressed: () => Navigator.pop(context, true),
              child: const Text('Eliminar'),
            ),
          ],
        ),
      );
      if (confirmed != true) return;
      final repository = ref.read(messagingRepositoryProvider);
      if (widget.internal) {
        await repository.softDeleteInternal(message.id);
        ref.invalidate(internalMessagesProvider(widget.conversationId));
      } else {
        await repository.softDelete(profile, message.id);
        ref.invalidate(messagesProvider(widget.conversationId));
        ref.invalidate(conversationsProvider);
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    final profile = ref.watch(sessionProvider).valueOrNull!.profile;
    final asyncMessages = widget.internal
        ? ref.watch(internalMessagesProvider(widget.conversationId))
        : ref.watch(messagesProvider(widget.conversationId));
    final conversations = widget.internal
        ? null
        : ref.watch(conversationsProvider).valueOrNull;
    final currentConversation = conversations
        ?.where((item) => item.id == widget.conversationId)
        .firstOrNull;
    final internalThread = widget.internal && widget.showInternalHeader
        ? _findThread(
            ref.watch(internalThreadsProvider).valueOrNull,
            widget.conversationId,
          )
        : null;
    return Column(
      children: [
        if (widget.internal && widget.showInternalHeader)
          Material(
            color: Theme.of(context).colorScheme.surface,
            child: Padding(
              padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 10),
              child: Align(
                alignment: Alignment.centerLeft,
                child: _InternalThreadIdentity(
                  thread: internalThread,
                  avatarRadius: 20,
                ),
              ),
            ),
          ),
        if (!widget.internal &&
            profile.type.name == 'staff' &&
            currentConversation != null)
          Material(
            color: Theme.of(context).colorScheme.surfaceContainerLow,
            child: Padding(
              padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 6),
              child: Row(
                children: [
                  const Text('Estado: '),
                  DropdownButton<String>(
                    value: currentConversation.state,
                    items: const [
                      DropdownMenuItem(
                        value: 'pendiente',
                        child: Text('Pendiente'),
                      ),
                      DropdownMenuItem(
                        value: 'en_curso',
                        child: Text('En curso'),
                      ),
                      DropdownMenuItem(
                        value: 'resuelta',
                        child: Text('Resuelta'),
                      ),
                    ],
                    onChanged: (value) async {
                      if (value == null) return;
                      await ref
                          .read(messagingRepositoryProvider)
                          .changeState(widget.conversationId, value);
                      ref.invalidate(conversationsProvider);
                    },
                  ),
                ],
              ),
            ),
          ),
        if (!widget.internal && profile.type.name == 'client')
          Material(
            color: Theme.of(context).colorScheme.secondaryContainer,
            child: const Padding(
              padding: EdgeInsets.symmetric(horizontal: 14, vertical: 8),
              child: Row(
                children: [
                  Icon(Icons.touch_app_outlined, size: 19),
                  SizedBox(width: 8),
                  Expanded(
                    child: Text(
                      'Pulsa sobre un mensaje para responderlo.',
                      style: TextStyle(fontSize: 13),
                    ),
                  ),
                ],
              ),
            ),
          ),
        Expanded(
          child: asyncMessages.when(
            loading: () => const Center(child: CircularProgressIndicator()),
            error: (error, _) => Center(child: Text(apiErrorMessage(error))),
            data: (messages) => ListView.builder(
              key: const Key('message-list'),
              controller: _scroll,
              padding: const EdgeInsets.symmetric(vertical: 14),
              itemCount: messages.length,
              itemBuilder: (context, index) {
                final message = messages[index];
                final mine =
                    message.authorId == profile.id ||
                    message.authorType == profile.type.name;
                return MessageBubble(
                  message: message,
                  mine: mine,
                  baseUrl: ref
                      .read(apiClientProvider)
                      .dio
                      .options
                      .baseUrl
                      .replaceAll(RegExp(r'/api/v1/messaging/?$'), ''),
                  authToken: ref.read(sessionProvider).valueOrNull?.token ?? '',
                  onReplyTap: message.replyTo == null
                      ? null
                      : () => _scrollToMessage(messages, message.replyTo!.id),
                  onAttachmentTap: _download,
                  onTap: message.deleted
                      ? null
                      : () => _messageActions(message, mine),
                  onLongPress: message.deleted
                      ? null
                      : () => _messageActions(message, mine),
                );
              },
            ),
          ),
        ),
        if (_replyingTo != null)
          Material(
            color: Theme.of(context).colorScheme.surfaceContainerHighest,
            child: ListTile(
              dense: true,
              leading: const Icon(Icons.reply),
              title: Text('Responder a ${_replyingTo!.authorName}'),
              subtitle: Text(
                _replyingTo!.body,
                maxLines: 1,
                overflow: TextOverflow.ellipsis,
              ),
              trailing: IconButton(
                onPressed: () => setState(() => _replyingTo = null),
                icon: const Icon(Icons.close),
              ),
            ),
          ),
        if (_files.isNotEmpty)
          SizedBox(
            height: 40,
            child: ListView(
              scrollDirection: Axis.horizontal,
              children: _files
                  .map(
                    (file) => Chip(
                      label: Text(file.name),
                      onDeleted: () => setState(() => _files.remove(file)),
                    ),
                  )
                  .toList(),
            ),
          ),
        SafeArea(
          top: false,
          child: Material(
            color: Colors.white,
            child: Padding(
              padding: const EdgeInsets.all(10),
              child: Row(
                crossAxisAlignment: CrossAxisAlignment.end,
                children: [
                  if (!widget.internal)
                    IconButton(
                      onPressed: _sending ? null : _pickFiles,
                      icon: const Icon(Icons.attach_file),
                    ),
                  Expanded(
                    child: TextField(
                      key: const Key('message-composer'),
                      controller: _body,
                      minLines: 1,
                      maxLines: 5,
                      decoration: const InputDecoration(
                        hintText: 'Escribe un mensaje...',
                        isDense: true,
                      ),
                    ),
                  ),
                  const SizedBox(width: 8),
                  IconButton.filled(
                    key: const Key('send-message'),
                    onPressed: _sending ? null : _send,
                    icon: _sending
                        ? const SizedBox.square(
                            dimension: 18,
                            child: CircularProgressIndicator(strokeWidth: 2),
                          )
                        : const Icon(Icons.send),
                  ),
                ],
              ),
            ),
          ),
        ),
      ],
    );
  }
}

InternalThread? _findThread(List<InternalThread>? threads, String id) {
  if (threads == null) return null;
  for (final thread in threads) {
    if (thread.id == id) return thread;
  }
  return null;
}

class _InternalThreadIdentity extends ConsumerWidget {
  const _InternalThreadIdentity({required this.thread, this.avatarRadius = 17});

  final InternalThread? thread;
  final double avatarRadius;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final current = thread;
    final title = current?.title ?? 'Chat interno';
    final subtitle = current == null
        ? 'Cargando información…'
        : current.kind == 'direct'
        ? 'Chat directo'
        : 'Grupo interno';
    final apiBaseUrl = ref
        .read(apiClientProvider)
        .dio
        .options
        .baseUrl
        .replaceAll(RegExp(r'/api/v1/messaging/?$'), '');
    final authToken = ref.read(sessionProvider).valueOrNull?.token ?? '';
    final initials = title
        .split(RegExp(r'\s+'))
        .where((part) => part.isNotEmpty)
        .take(2)
        .map((part) => part[0])
        .join()
        .toUpperCase();
    return Row(
      mainAxisSize: MainAxisSize.min,
      children: [
        if (current?.kind == 'direct')
          AuthenticatedAvatar(
            radius: avatarRadius,
            baseUrl: apiBaseUrl,
            authToken: authToken,
            imagePath: current?.counterpartAvatarUrl ?? '',
            fallbackText: initials.isEmpty ? '?' : initials,
            cacheVersion: current?.id ?? '',
          )
        else
          CircleAvatar(
            radius: avatarRadius,
            child: const Icon(Icons.groups_outlined),
          ),
        const SizedBox(width: 10),
        Flexible(
          child: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(title, maxLines: 1, overflow: TextOverflow.ellipsis),
              Text(
                subtitle,
                maxLines: 1,
                overflow: TextOverflow.ellipsis,
                style: Theme.of(context).textTheme.bodySmall,
              ),
            ],
          ),
        ),
      ],
    );
  }
}
