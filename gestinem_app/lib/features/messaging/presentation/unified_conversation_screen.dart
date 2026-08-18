import 'dart:async';

import 'package:file_picker/file_picker.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../core/api/api_client.dart';
import '../../../core/config/app_config.dart';
import '../../auth/presentation/auth_controller.dart';
import '../domain/message.dart';
import 'message_bubble.dart';
import 'messaging_providers.dart';

class UnifiedConversationScreen extends ConsumerStatefulWidget {
  const UnifiedConversationScreen({super.key});

  @override
  ConsumerState<UnifiedConversationScreen> createState() =>
      _UnifiedConversationScreenState();
}

class _UnifiedConversationScreenState
    extends ConsumerState<UnifiedConversationScreen> {
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
    try {
      await ref.read(messagingRepositoryProvider).markAllRead();
      ref.invalidate(unifiedConversationProvider);
    } catch (_) {}
  }

  Future<void> _pickFiles() async {
    final result = await FilePicker.pickFiles(
      allowedExtensions: [
        'pdf', 'png', 'jpg', 'jpeg', 'gif', 'tif', 'tiff',
        'txt', 'xml', 'csv', 'xls', 'xlsx', 'doc', 'docx', 'zip',
      ],
      type: FileType.custom,
    );
    if (result.isNotEmpty) setState(() => _files = result);
  }

  Future<void> _send() async {
    if ((_body.text.trim().isEmpty && _files.isEmpty) || _sending) return;
    setState(() => _sending = true);
    try {
      await ref.read(messagingRepositoryProvider).sendUnified(
            _body.text,
            _files,
            replyToMessageId: _replyingTo?.id,
          );
      _body.clear();
      setState(() {
        _files = [];
        _replyingTo = null;
      });
      ref.invalidate(unifiedMessagesProvider);
      ref.invalidate(unifiedConversationProvider);
      WidgetsBinding.instance.addPostFrameCallback((_) {
        if (_scroll.hasClients) {
          _scroll.animateTo(
            _scroll.position.maxScrollExtent,
            duration: const Duration(milliseconds: 300),
            curve: Curves.easeOut,
          );
        }
      });
    } catch (error) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text(apiErrorMessage(error))),
        );
      }
    } finally {
      if (mounted) setState(() => _sending = false);
    }
  }

  void _scrollToMessage(List<Message> messages, String id) {
    final index = messages.indexWhere((m) => m.id == id);
    if (index >= 0 && _scroll.hasClients) {
      _scroll.animateTo(
        index * 80.0,
        duration: const Duration(milliseconds: 350),
        curve: Curves.easeOut,
      );
    }
  }

  Future<void> _download(Attachment attachment) async {
    try {
      final profile = ref.read(sessionProvider).valueOrNull!.profile;
      final bytes =
          await ref.read(messagingRepositoryProvider).download(profile, attachment);
      await FilePicker.saveFile(
        fileName: attachment.name,
        bytes: bytes,
        mimeType: attachment.contentType,
      );
    } catch (error) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text(apiErrorMessage(error))),
        );
      }
    }
  }

  Future<void> _messageActions(Message message) async {
    final action = await showModalBottomSheet<String>(
      context: context,
      builder: (ctx) => SafeArea(
        child: Wrap(children: [
          ListTile(
            leading: const Icon(Icons.reply),
            title: const Text('Responder'),
            onTap: () => Navigator.pop(ctx, 'reply'),
          ),
        ]),
      ),
    );
    if (!mounted) return;
    if (action == 'reply') setState(() => _replyingTo = message);
  }

  @override
  Widget build(BuildContext context) {
    final asyncMessages = ref.watch(unifiedMessagesProvider);
    final baseUrl = appConfig.apiBaseUrl.replaceAll('/api/v1/messaging', '');

    return Scaffold(
      appBar: AppBar(
        title: Row(children: [
          Image.asset('assets/images/logo.png', height: 28, semanticLabel: 'Gestinem'),
          const SizedBox(width: 10),
          const Text('Gestinem'),
        ]),
        actions: [
          IconButton(
            onPressed: () {
              ref.invalidate(unifiedMessagesProvider);
              ref.invalidate(unifiedConversationProvider);
            },
            icon: const Icon(Icons.refresh),
          ),
        ],
      ),
      body: Column(children: [
        Expanded(
          child: asyncMessages.when(
            loading: () => const Center(child: CircularProgressIndicator()),
            error: (error, _) => Center(
              child: Column(mainAxisSize: MainAxisSize.min, children: [
                Text(apiErrorMessage(error), textAlign: TextAlign.center),
                const SizedBox(height: 12),
                FilledButton(
                  onPressed: () => ref.invalidate(unifiedMessagesProvider),
                  child: const Text('Reintentar'),
                ),
              ]),
            ),
            data: (messages) {
              if (messages.isEmpty) {
                return const Center(
                  child: Column(mainAxisSize: MainAxisSize.min, children: [
                    Icon(Icons.forum_outlined, size: 48, color: Colors.grey),
                    SizedBox(height: 12),
                    Text(
                      'No hay mensajes todavía.\nEscribe para iniciar la conversación.',
                      textAlign: TextAlign.center,
                    ),
                  ]),
                );
              }
              return ListView.builder(
                key: const Key('unified-message-list'),
                controller: _scroll,
                padding: const EdgeInsets.symmetric(vertical: 14),
                itemCount: messages.length,
                itemBuilder: (context, index) {
                  final message = messages[index];
                  final profile = ref.read(sessionProvider).valueOrNull!.profile;
                  final mine = message.authorType == 'client' &&
                      message.authorId == profile.id;
                  final showDate = index == 0 ||
                      !_sameDay(messages[index - 1].createdAt, message.createdAt);
                  return Column(children: [
                    if (showDate) _DateSeparator(date: message.createdAt),
                    MessageBubble(
                      message: message,
                      mine: mine,
                      baseUrl: baseUrl,
                      authToken: ref.read(sessionProvider).valueOrNull?.token ?? '',
                      onReplyTap: message.replyTo == null
                          ? null
                          : () => _scrollToMessage(messages, message.replyTo!.id),
                      onAttachmentTap: _download,
                      onTap: message.deleted ? null : () => _messageActions(message),
                      onLongPress:
                          message.deleted ? null : () => _messageActions(message),
                    ),
                  ]);
                },
              );
            },
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
                  .map((f) => Chip(
                        label: Text(f.name),
                        onDeleted: () =>
                            setState(() => _files.remove(f)),
                      ))
                  .toList(),
            ),
          ),
        SafeArea(
          top: false,
          child: Material(
            color: Theme.of(context).colorScheme.surface,
            elevation: 2,
            child: Padding(
              padding: const EdgeInsets.all(10),
              child: Row(
                crossAxisAlignment: CrossAxisAlignment.end,
                children: [
                  IconButton(
                    onPressed: _sending ? null : _pickFiles,
                    icon: const Icon(Icons.attach_file),
                  ),
                  Expanded(
                    child: TextField(
                      key: const Key('unified-message-composer'),
                      controller: _body,
                      minLines: 1,
                      maxLines: 5,
                      decoration: const InputDecoration(
                        hintText: 'Escribe un mensaje...',
                        isDense: true,
                        border: InputBorder.none,
                      ),
                    ),
                  ),
                  const SizedBox(width: 8),
                  IconButton.filled(
                    key: const Key('unified-send-message'),
                    onPressed: _sending ? null : _send,
                    icon: _sending
                        ? const SizedBox.square(
                            dimension: 18,
                            child:
                                CircularProgressIndicator(strokeWidth: 2),
                          )
                        : const Icon(Icons.send),
                  ),
                ],
              ),
            ),
          ),
        ),
      ]),
    );
  }

  bool _sameDay(DateTime a, DateTime b) =>
      a.year == b.year && a.month == b.month && a.day == b.day;
}

class _DateSeparator extends StatelessWidget {
  const _DateSeparator({required this.date});
  final DateTime date;

  @override
  Widget build(BuildContext context) {
    final now = DateTime.now();
    String label;
    if (date.year == now.year && date.month == now.month && date.day == now.day) {
      label = 'Hoy';
    } else if (date.year == now.year &&
        date.month == now.month &&
        date.day == now.day - 1) {
      label = 'Ayer';
    } else {
      label =
          '${date.day.toString().padLeft(2, '0')}/${date.month.toString().padLeft(2, '0')}/${date.year}';
    }
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 8),
      child: Row(children: [
        const Expanded(child: Divider()),
        Padding(
          padding: const EdgeInsets.symmetric(horizontal: 12),
          child: Text(
            label,
            style: Theme.of(context).textTheme.labelSmall?.copyWith(
                  color: Theme.of(context).colorScheme.onSurfaceVariant,
                ),
          ),
        ),
        const Expanded(child: Divider()),
      ]),
    );
  }
}
