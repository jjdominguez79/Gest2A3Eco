import 'dart:async';

import 'package:file_picker/file_picker.dart';
import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../core/api/api_client.dart';
import '../../../core/config/app_config.dart';
import '../../../core/files/archivo_descargado.dart';
import '../../../core/text/sentence_capitalization_formatter.dart';
import '../../auth/presentation/auth_controller.dart';
import '../domain/message.dart';
import 'message_bubble.dart';
import 'message_edit_dialogs.dart';
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
  final _composerFocus = FocusNode();
  final _scroll = ScrollController(keepScrollOffset: false);
  List<PlatformFile> _files = [];
  Message? _replyingTo;
  bool _sending = false;
  String? _lastMessageMarkedRead;
  String? _messagePendingScrollId;
  final List<Message> _olderMessages = [];
  bool _loadingEarlier = false;
  bool _hasEarlier = true;
  String? _oldestMessageId;

  @override
  void initState() {
    super.initState();
    _scroll.addListener(_loadEarlierWhenNeeded);
    WidgetsBinding.instance.addPostFrameCallback((_) => _markRead());
  }

  @override
  void dispose() {
    _body.dispose();
    _composerFocus.dispose();
    _scroll.dispose();
    super.dispose();
  }

  Future<void> _markRead() async {
    try {
      await ref.read(messagingRepositoryProvider).markAllRead();
      ref.invalidate(unifiedConversationProvider);
    } catch (_) {}
  }

  void _loadEarlierWhenNeeded() {
    if (!_scroll.hasClients || _loadingEarlier || !_hasEarlier) return;
    if (_scroll.position.pixels >= _scroll.position.maxScrollExtent - 160) {
      unawaited(_loadEarlier());
    }
  }

  Future<void> _loadEarlier() async {
    final before = _oldestMessageId;
    if (before == null || _loadingEarlier || !_hasEarlier) return;
    setState(() => _loadingEarlier = true);
    try {
      final page = await ref.read(messagingRepositoryProvider).unifiedMessages(
        beforeMessageId: before,
      );
      if (!mounted) return;
      final known = _olderMessages.map((message) => message.id).toSet();
      setState(() {
        _olderMessages.insertAll(
          0,
          page.where((message) => known.add(message.id)),
        );
        _hasEarlier = page.length == 100;
        if (_olderMessages.isNotEmpty) {
          _oldestMessageId = _olderMessages.first.id;
        }
      });
    } finally {
      if (mounted) setState(() => _loadingEarlier = false);
    }
  }

  void _markReadWhenMessagesArrive(List<Message> messages) {
    if (messages.isEmpty) return;
    final lastMessageId = messages.last.id;
    if (_lastMessageMarkedRead == lastMessageId) return;
    _lastMessageMarkedRead = lastMessageId;
    unawaited(_markRead());
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
    if ((_body.text.trim().isEmpty && _files.isEmpty) || _sending) return;
    final restoreComposerFocus = _body.text.trim().isNotEmpty;
    if (restoreComposerFocus) _composerFocus.requestFocus();
    setState(() => _sending = true);
    try {
      final sentMessage = await ref
          .read(messagingRepositoryProvider)
          .sendUnified(_body.text, _files, replyToMessageId: _replyingTo?.id);
      if (!mounted) return;
      _messagePendingScrollId = sentMessage.id;
      if (restoreComposerFocus) _composerFocus.requestFocus();
      _body.clear();
      setState(() {
        _files = [];
        _replyingTo = null;
      });
      ref.invalidate(unifiedMessagesProvider);
      ref.invalidate(unifiedConversationProvider);
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

  void _scrollToSentMessageWhenReady(List<Message> messages) {
    final messageId = _messagePendingScrollId;
    if (messageId == null ||
        !messages.any((message) => message.id == messageId)) {
      return;
    }
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (!mounted ||
          _messagePendingScrollId != messageId ||
          !_scroll.hasClients) {
        return;
      }
      _messagePendingScrollId = null;
      unawaited(_animateToBottom());
    });
  }

  Future<void> _animateToBottom() async {
    for (var attempt = 0; attempt < 3; attempt++) {
      if (!mounted || !_scroll.hasClients) return;
      await _scroll.animateTo(
        _scroll.position.minScrollExtent,
        duration: Duration(milliseconds: attempt == 0 ? 300 : 100),
        curve: Curves.easeOut,
      );
      await WidgetsBinding.instance.endOfFrame;
      if (!mounted || !_scroll.hasClients) return;
      if ((_scroll.position.minScrollExtent - _scroll.position.pixels).abs() <
          1) {
        return;
      }
    }
    if (mounted && _scroll.hasClients) {
      _scroll.jumpTo(_scroll.position.minScrollExtent);
    }
  }

  void _scrollToMessage(List<Message> messages, String id) {
    final index = messages.indexWhere((m) => m.id == id);
    if (index >= 0 && _scroll.hasClients) {
      _scroll.animateTo(
        (messages.length - 1 - index) * 80.0,
        duration: const Duration(milliseconds: 350),
        curve: Curves.easeOut,
      );
    }
  }

  /// Descarga un adjunto saliente y confirma al backend tras guardar.
  Future<void> _download(Attachment attachment) async {
    final apertura = prepararAperturaArchivoDescargado();
    final repository = ref.read(messagingRepositoryProvider);
    try {
      final (bytes, downloadId) = await repository.downloadWithId(attachment);
      final savedUri = await FilePicker.saveFile(
        fileName: attachment.name,
        bytes: bytes,
        mimeType: attachment.contentType,
      );
      if (savedUri == null && !kIsWeb) {
        cancelarAperturaArchivoDescargado(apertura);
        return;
      }
      final abierto = await abrirArchivoDescargado(
        apertura,
        uriGuardado: savedUri,
        bytes: bytes,
        fileName: attachment.name,
        contentType: attachment.contentType,
      );
      var confirmed = downloadId.isEmpty;
      if (downloadId.isNotEmpty) {
        for (var attempt = 0; attempt < 3 && !confirmed; attempt++) {
          try {
            await repository.confirmDownload(attachment.id, downloadId);
            confirmed = true;
          } catch (_) {
            if (attempt < 2) {
              await Future<void>.delayed(const Duration(milliseconds: 400));
            }
          }
        }
      }
      if (!mounted) return;
      ref.invalidate(unifiedMessagesProvider);
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text(
            confirmed
                ? abierto
                      ? 'Documento guardado, abierto y descarga registrada.'
                      : 'Documento guardado y descarga registrada; no se pudo abrir automaticamente.'
                : 'Documento guardado, pero no se pudo registrar la descarga.',
          ),
        ),
      );
    } catch (error) {
      cancelarAperturaArchivoDescargado(apertura);
      if (mounted) {
        ScaffoldMessenger.of(
          context,
        ).showSnackBar(SnackBar(content: Text(apiErrorMessage(error))));
      }
    }
  }

  Future<void> _messageActions(Message message) async {
    final profile = ref.read(sessionProvider).valueOrNull!.profile;
    final mine =
        message.authorType == profile.type.name &&
        message.authorId == profile.id;
    final action = await showModalBottomSheet<String>(
      context: context,
      builder: (ctx) => SafeArea(
        child: Wrap(
          children: [
            ListTile(
              leading: const Icon(Icons.reply),
              title: const Text('Responder'),
              onTap: () => Navigator.pop(ctx, 'reply'),
            ),
            if (mine && !message.deleted)
              ListTile(
                key: const Key('edit-message-option'),
                leading: const Icon(Icons.edit_outlined),
                title: const Text('Editar mensaje'),
                onTap: () => Navigator.pop(ctx, 'edit'),
              ),
          ],
        ),
      ),
    );
    if (!mounted) return;
    if (action == 'reply') setState(() => _replyingTo = message);
    if (action == 'edit') {
      final repository = ref.read(messagingRepositoryProvider);
      final cambiado = await editarMensaje(context, message, (texto) async {
        await repository.edit(profile, message, texto);
      });
      if (!mounted || !cambiado) return;
      if (_replyingTo?.id == message.id) setState(() => _replyingTo = null);
      ref.invalidate(unifiedMessagesProvider);
      ref.invalidate(unifiedConversationProvider);
    }
  }

  @override
  Widget build(BuildContext context) {
    final asyncMessages = ref.watch(unifiedMessagesProvider);
    asyncMessages.whenData(_markReadWhenMessagesArrive);
    final baseUrl = appConfig.apiBaseUrl.replaceAll('/api/v1/messaging', '');

    return Scaffold(
      appBar: AppBar(
        title: Row(
          children: [
            Image.asset(
              'assets/images/logo.png',
              height: 28,
              semanticLabel: 'Gestinem',
            ),
            const SizedBox(width: 10),
            const Text('Gestinem'),
          ],
        ),
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
      body: Column(
        children: [
          Expanded(
            child: asyncMessages.when(
              loading: () => const Center(child: CircularProgressIndicator()),
              error: (error, _) => Center(
                child: Column(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    Text(apiErrorMessage(error), textAlign: TextAlign.center),
                    const SizedBox(height: 12),
                    FilledButton(
                      onPressed: () => ref.invalidate(unifiedMessagesProvider),
                      child: const Text('Reintentar'),
                    ),
                  ],
                ),
              ),
              data: (latestMessages) {
                final byId = <String, Message>{
                  for (final message in _olderMessages) message.id: message,
                  for (final message in latestMessages) message.id: message,
                };
                final messages = byId.values.toList()
                  ..sort((a, b) {
                    final byDate = a.createdAt.compareTo(b.createdAt);
                    return byDate != 0 ? byDate : a.id.compareTo(b.id);
                  });
                _oldestMessageId = messages.firstOrNull?.id;
                if (_olderMessages.isEmpty && latestMessages.length < 100) {
                  _hasEarlier = false;
                }
                _scrollToSentMessageWhenReady(messages);
                if (messages.isEmpty) {
                  return const Center(
                    child: Column(
                      mainAxisSize: MainAxisSize.min,
                      children: [
                        Icon(
                          Icons.forum_outlined,
                          size: 48,
                          color: Colors.grey,
                        ),
                        SizedBox(height: 12),
                        Text(
                          'No hay mensajes todavía.\nEscribe para iniciar la conversación.',
                          textAlign: TextAlign.center,
                        ),
                      ],
                    ),
                  );
                }
                return Scrollbar(
                  controller: _scroll,
                  child: ListView.builder(
                    key: const Key('unified-message-list'),
                    controller: _scroll,
                    reverse: true,
                    padding: const EdgeInsets.symmetric(vertical: 14),
                    itemCount: messages.length + (_loadingEarlier ? 1 : 0),
                    itemBuilder: (context, index) {
                      if (_loadingEarlier && index == messages.length) {
                        return const Padding(
                          padding: EdgeInsets.all(12),
                          child: Center(child: CircularProgressIndicator()),
                        );
                      }
                      final messageIndex = messages.length - 1 - index;
                      final message = messages[messageIndex];
                      final profile = ref
                          .read(sessionProvider)
                          .valueOrNull!
                          .profile;
                      final mine =
                          message.authorType == 'client' &&
                          message.authorId == profile.id;
                      final showDate =
                          messageIndex == 0 ||
                          !_sameDay(
                            messages[messageIndex - 1].createdAt,
                            message.createdAt,
                          );
                      return Column(
                        children: [
                          if (showDate) _DateSeparator(date: message.createdAt),
                          MessageBubble(
                            message: message,
                            mine: mine,
                            baseUrl: baseUrl,
                            authToken:
                                ref.read(sessionProvider).valueOrNull?.token ??
                                '',
                            onReplyTap: message.replyTo == null
                                ? null
                                : () => _scrollToMessage(
                                    messages,
                                    message.replyTo!.id,
                                  ),
                            onAttachmentTap: _download,
                            onTap: message.deleted
                                ? null
                                : () => _messageActions(message),
                            onLongPress: message.deleted
                                ? null
                                : () => _messageActions(message),
                          ),
                        ],
                      );
                    },
                  ),
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
                    .map(
                      (f) => Chip(
                        label: Text(f.name),
                        onDeleted: () => setState(() => _files.remove(f)),
                      ),
                    )
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
                        focusNode: _composerFocus,
                        textCapitalization: TextCapitalization.sentences,
                        inputFormatters: const [
                          SentenceCapitalizationFormatter(),
                        ],
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
      ),
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
    if (date.year == now.year &&
        date.month == now.month &&
        date.day == now.day) {
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
      child: Row(
        children: [
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
        ],
      ),
    );
  }
}
