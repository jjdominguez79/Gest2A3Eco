import 'dart:async';

import 'package:file_picker/file_picker.dart';
import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:record/record.dart';

import '../../../core/api/api_client.dart';
import '../../../core/files/archivo_descargado.dart';
import '../../../core/notifications/notifications_service.dart';
import '../../../core/text/sentence_capitalization_formatter.dart';
import '../../../core/widgets/authenticated_avatar.dart';
import '../../auth/domain/user_profile.dart';
import '../../auth/presentation/auth_controller.dart';
import '../domain/conversation.dart';
import '../domain/message.dart';
import 'message_bubble.dart';
import 'message_edit_dialogs.dart';
import 'messaging_providers.dart';
import 'voice_recording.dart';

class ConversationScreen extends ConsumerWidget {
  const ConversationScreen({
    super.key,
    required this.conversationId,
    this.internal = false,
    this.initialDraft,
  });
  final String conversationId;
  final bool internal;
  final String? initialDraft;

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
          onPressed: () => context.go('/'),
          icon: const Icon(Icons.arrow_back),
        ),
        title: internal
            ? _InternalThreadIdentity(thread: thread)
            : const Text('Conversación'),
      ),
      body: ConversationView(
        conversationId: conversationId,
        internal: internal,
        initialDraft: initialDraft,
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
    this.initialDraft,
  });
  final String conversationId;
  final bool internal;
  final bool showInternalHeader;
  final String? initialDraft;

  @override
  ConsumerState<ConversationView> createState() => _ConversationViewState();
}

class _ConversationViewState extends ConsumerState<ConversationView> {
  final _body = TextEditingController();
  final _composerFocus = FocusNode();
  final _scroll = ScrollController(keepScrollOffset: false);
  List<PlatformFile> _files = [];
  Message? _replyingTo;
  bool _sending = false;
  final AudioRecorder _recorder = AudioRecorder();
  StreamSubscription<Uint8List>? _recordingSubscription;
  Completer<void>? _recordingDone;
  Timer? _recordingTimer;
  final List<int> _recordingBytes = [];
  bool _recording = false;
  int _recordingSeconds = 0;
  AudioEncoder _voiceEncoder = AudioEncoder.aacLc;
  String _voiceExtension = 'aac';
  int _voiceSampleRate = voiceSampleRate;
  int _voiceChannelCount = voiceChannelCount;
  String? _lastMessageMarkedRead;
  String? _messagePendingScrollId;
  bool _initialScrollPending = true;
  bool _initialScrollScheduled = false;
  Timer? _presenceTimer;
  late final NotificationsService _notificationsService;

  @override
  void initState() {
    super.initState();
    _body.text = widget.initialDraft ?? '';
    _notificationsService = ref.read(notificationsServiceProvider);
    WidgetsBinding.instance.addPostFrameCallback((_) {
      _activateConversation();
      _markRead();
    });
  }

  @override
  void didUpdateWidget(covariant ConversationView oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (oldWidget.conversationId != widget.conversationId ||
        oldWidget.internal != widget.internal) {
      _lastMessageMarkedRead = null;
      _messagePendingScrollId = null;
      _initialScrollPending = true;
      _initialScrollScheduled = false;
      WidgetsBinding.instance.addPostFrameCallback((_) {
        _activateConversation();
        _markRead();
      });
    }
  }

  @override
  void dispose() {
    _presenceTimer?.cancel();
    _recordingTimer?.cancel();
    unawaited(_recordingSubscription?.cancel());
    unawaited(_recorder.dispose());
    unawaited(_notificationsService.clearActiveTarget());
    _body.dispose();
    _composerFocus.dispose();
    _scroll.dispose();
    super.dispose();
  }

  void _activateConversation() {
    _presenceTimer?.cancel();
    final service = _notificationsService;
    final type = widget.internal ? 'internal_thread' : 'conversation';
    unawaited(service.setActiveTarget(type, widget.conversationId));
    _presenceTimer = Timer.periodic(
      const Duration(seconds: 30),
      (_) => unawaited(service.setActiveTarget(type, widget.conversationId)),
    );
  }

  Future<void> _markRead() async {
    try {
      final repository = ref.read(messagingRepositoryProvider);
      if (widget.internal) {
        await repository.markInternalRead(widget.conversationId);
        await _notificationsService.cancelTarget(
          'internal_thread',
          widget.conversationId,
        );
        ref.invalidate(internalThreadsProvider);
      } else {
        final profile = ref.read(sessionProvider).valueOrNull?.profile;
        if (profile == null) return;
        await repository.markRead(profile, widget.conversationId);
        await _notificationsService.cancelTarget(
          'conversation',
          widget.conversationId,
        );
        ref.invalidate(conversationsProvider);
        ref.invalidate(unifiedConversationProvider);
      }
    } catch (error, stackTrace) {
      debugPrint(
        'No se pudo actualizar el estado de lectura: $error\n$stackTrace',
      );
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
    const extensions = [
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
    ];
    final List<PlatformFile> result;
    if (widget.internal) {
      result = await FilePicker.pickFiles(
        allowedExtensions: extensions,
        type: FileType.custom,
      );
    } else {
      final file = await FilePicker.pickFile(
        allowedExtensions: extensions,
        type: FileType.custom,
      );
      result = [?file];
    }
    if (result.isNotEmpty) setState(() => _files = result);
  }

  Future<void> _startVoiceRecording() async {
    if (_sending || _recording) return;
    try {
      if (!await _recorder.hasPermission()) {
        if (mounted) {
          ScaffoldMessenger.of(context).showSnackBar(
            const SnackBar(
              content: Text('Autoriza el acceso al microfono para grabar.'),
            ),
          );
        }
        return;
      }
      final candidates = voiceStreamEncoderCandidates(
        isWeb: kIsWeb,
        platform: defaultTargetPlatform,
      );
      AudioEncoder? encoder;
      for (final candidate in candidates) {
        if (await _recorder.isEncoderSupported(candidate)) {
          encoder = candidate;
          break;
        }
      }
      if (encoder == null) {
        throw UnsupportedError(
          'Este dispositivo no admite grabacion de audio en streaming.',
        );
      }
      _voiceEncoder = encoder;
      _voiceExtension = voiceStreamExtension(encoder);
      _voiceSampleRate = voiceSampleRate;
      _voiceChannelCount = voiceChannelCount;
      await _recorder.setOnConfigChanged((config) {
        _voiceSampleRate = config.sampleRate;
        _voiceChannelCount = config.numChannels;
      });
      _recordingBytes.clear();
      _recordingDone = Completer<void>();
      final stream = await _recorder.startStream(
        RecordConfig(
          encoder: encoder,
          bitRate: 64000,
          sampleRate: voiceSampleRate,
          numChannels: voiceChannelCount,
        ),
      );
      _recordingSubscription = stream.listen(
        _recordingBytes.addAll,
        onDone: () {
          if (!(_recordingDone?.isCompleted ?? true)) {
            _recordingDone!.complete();
          }
        },
      );
      if (!mounted) return;
      setState(() {
        _recording = true;
        _recordingSeconds = 0;
      });
      _recordingTimer = Timer.periodic(const Duration(seconds: 1), (_) {
        if (!mounted) return;
        if (_recordingSeconds >= 299) {
          unawaited(_stopVoiceRecording(send: true));
        } else {
          setState(() => _recordingSeconds++);
        }
      });
    } catch (error) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text('No se pudo iniciar la grabacion: $error')),
        );
      }
    }
  }

  Future<void> _stopVoiceRecording({required bool send}) async {
    if (!_recording) return;
    _recordingTimer?.cancel();
    setState(() => _recording = false);
    try {
      if (send) {
        await _recorder.stop();
      } else {
        await _recorder.cancel();
      }
      try {
        await _recordingDone?.future.timeout(const Duration(seconds: 2));
      } on TimeoutException {
        // Algunos dispositivos no cierran el stream de forma inmediata.
      }
      await _recordingSubscription?.cancel();
      if (!send || _recordingBytes.isEmpty) return;
      final bytes = finalizeVoiceStream(
        _voiceEncoder,
        _recordingBytes,
        sampleRate: _voiceSampleRate,
        channels: _voiceChannelCount,
      );
      _files = [
        _VoicePlatformFile(
          name:
              'nota_voz_${DateTime.now().millisecondsSinceEpoch}.$_voiceExtension',
          bytes: bytes,
        ),
      ];
      await _send();
    } catch (error) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text('No se pudo enviar la nota de voz: $error')),
        );
      }
    } finally {
      _recordingBytes.clear();
      _recordingSeconds = 0;
    }
  }

  String _recordingTime() {
    final minutes = (_recordingSeconds ~/ 60).toString().padLeft(2, '0');
    final seconds = (_recordingSeconds % 60).toString().padLeft(2, '0');
    return '$minutes:$seconds';
  }

  Future<void> _send({bool keepComposerFocus = false}) async {
    if (_body.text.trim().isEmpty && _files.isEmpty || _sending) return;
    final restoreComposerFocus =
        keepComposerFocus && _body.text.trim().isNotEmpty;
    if (restoreComposerFocus) _composerFocus.requestFocus();
    setState(() => _sending = true);
    try {
      final repository = ref.read(messagingRepositoryProvider);
      final Message sentMessage;
      if (widget.internal) {
        sentMessage = await repository.sendInternal(
          widget.conversationId,
          _body.text,
          _files,
          replyToMessageId: _replyingTo?.id,
        );
      } else {
        final profile = ref.read(sessionProvider).valueOrNull!.profile;
        sentMessage = await repository.send(
          profile,
          widget.conversationId,
          _body.text,
          _files,
          replyToMessageId: _replyingTo?.id,
        );
      }
      if (!mounted) return;
      _messagePendingScrollId = sentMessage.id;
      if (restoreComposerFocus) _composerFocus.requestFocus();
      _body.clear();
      setState(() {
        _files = [];
        _replyingTo = null;
      });
      if (widget.internal) {
        ref.invalidate(internalMessagesProvider(widget.conversationId));
      } else {
        ref.invalidate(messagesProvider(widget.conversationId));
        ref.invalidate(conversationsProvider);
      }
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

  void _scrollToBottomWhenOpened(List<Message> messages) {
    if (messages.isEmpty || !_initialScrollPending || _initialScrollScheduled) {
      return;
    }
    _initialScrollScheduled = true;
    final conversationId = widget.conversationId;
    final internal = widget.internal;
    WidgetsBinding.instance.addPostFrameCallback((_) {
      _initialScrollScheduled = false;
      if (!mounted ||
          !_initialScrollPending ||
          conversationId != widget.conversationId ||
          internal != widget.internal ||
          !_scroll.hasClients) {
        return;
      }
      _initialScrollPending = false;
      // La lista invertida ancla el ultimo mensaje sin estimar el historial.
      _scroll.jumpTo(_scroll.position.minScrollExtent);
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
    final index = messages.indexWhere((message) => message.id == id);
    if (index >= 0 && _scroll.hasClients) {
      _scroll.animateTo(
        (messages.length - 1 - index) * 96.0,
        duration: const Duration(milliseconds: 350),
        curve: Curves.easeOut,
      );
    }
  }

  /// Descarga un adjunto saliente (solo cliente) y confirma al backend.
  Future<void> _download(Attachment attachment) async {
    final apertura = prepararAperturaArchivoDescargado();
    final repository = ref.read(messagingRepositoryProvider);
    try {
      if (widget.internal) {
        final bytes = await repository.downloadInternalAttachment(
          attachment.id,
        );
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
        if (!mounted) return;
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(
            content: Text(
              abierto
                  ? 'Archivo guardado y abierto.'
                  : 'Archivo guardado. No se pudo abrir automaticamente.',
            ),
          ),
        );
        return;
      }
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
      ref.invalidate(messagesProvider(widget.conversationId));
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

  Future<Uint8List> _loadVoice(Attachment attachment) async {
    final repository = ref.read(messagingRepositoryProvider);
    if (widget.internal) {
      return repository.downloadInternalAttachment(attachment.id);
    }
    final profile = ref.read(sessionProvider).valueOrNull!.profile;
    return repository.download(profile, attachment);
  }

  String _fmtAuditDate(DateTime value) =>
      '${value.day.toString().padLeft(2, '0')}/'
      '${value.month.toString().padLeft(2, '0')}/${value.year} '
      '${value.hour.toString().padLeft(2, '0')}:'
      '${value.minute.toString().padLeft(2, '0')}';

  Future<void> _showAttachmentHistory(Attachment attachment) async {
    try {
      final rows = await ref
          .read(messagingRepositoryProvider)
          .attachmentDownloads(attachment.id);
      if (!mounted) return;
      await showDialog<void>(
        context: context,
        builder: (context) => AlertDialog(
          title: Text('Descargas de ${attachment.name}'),
          content: SizedBox(
            width: 620,
            child: rows.isEmpty
                ? const Text(
                    'El cliente todavía no ha descargado el documento.',
                  )
                : ListView.separated(
                    shrinkWrap: true,
                    itemCount: rows.length,
                    separatorBuilder: (_, _) => const Divider(),
                    itemBuilder: (_, index) {
                      final row = rows[index];
                      return ListTile(
                        contentPadding: EdgeInsets.zero,
                        leading: Icon(
                          row.completedAt != null
                              ? Icons.verified_outlined
                              : Icons.downloading_outlined,
                        ),
                        title: Text(
                          row.clientName.isEmpty ? 'Cliente' : row.clientName,
                        ),
                        subtitle: Text(
                          'Iniciada: ${_fmtAuditDate(row.downloadedAt)}\n'
                          'Completada: ${row.completedAt == null ? 'No confirmada' : _fmtAuditDate(row.completedAt!)}\n'
                          'IP: ${row.ip.isEmpty ? 'No disponible' : row.ip}\n'
                          'Dispositivo: ${row.userAgent.isEmpty ? 'No disponible' : row.userAgent}'
                          '${row.sha256.isEmpty ? '' : '\nHuella SHA-256: ${row.sha256}'}',
                        ),
                      );
                    },
                  ),
          ),
          actions: [
            TextButton(
              onPressed: () => Navigator.pop(context),
              child: const Text('Cerrar'),
            ),
          ],
        ),
      );
    } catch (error) {
      if (mounted) {
        ScaffoldMessenger.of(
          context,
        ).showSnackBar(SnackBar(content: Text(apiErrorMessage(error))));
      }
    }
  }

  Future<void> _withdrawAttachment(Attachment attachment) async {
    final reason = TextEditingController();
    final accepted = await showDialog<bool>(
      context: context,
      builder: (context) => AlertDialog(
        title: const Text('Retirar documento'),
        content: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text('El cliente dejará de poder descargar ${attachment.name}.'),
            const SizedBox(height: 12),
            TextField(
              controller: reason,
              autofocus: true,
              maxLength: 500,
              decoration: const InputDecoration(
                labelText: 'Motivo obligatorio',
                border: OutlineInputBorder(),
              ),
            ),
          ],
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(context, false),
            child: const Text('Cancelar'),
          ),
          FilledButton(
            onPressed: () {
              if (reason.text.trim().isNotEmpty) Navigator.pop(context, true);
            },
            child: const Text('Retirar'),
          ),
        ],
      ),
    );
    if (accepted != true) {
      reason.dispose();
      return;
    }
    final value = reason.text.trim();
    reason.dispose();
    try {
      await ref
          .read(messagingRepositoryProvider)
          .withdrawAttachment(attachment.id, value);
      ref.invalidate(messagesProvider(widget.conversationId));
      ref.invalidate(conversationsProvider);
      if (mounted) {
        ScaffoldMessenger.of(
          context,
        ).showSnackBar(const SnackBar(content: Text('Documento retirado.')));
      }
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
    // Los mensajes con adjuntos no pueden eliminarse
    final canDelete =
        !message.deleted &&
        (mine || profile.isAdmin) &&
        (widget.internal || !message.hasAttachments);
    final action = await showModalBottomSheet<String>(
      context: context,
      builder: (context) => SafeArea(
        child: Wrap(
          children: [
            if (!message.deleted)
              ListTile(
                leading: const Icon(Icons.reply),
                title: const Text('Responder'),
                onTap: () => Navigator.pop(context, 'reply'),
              ),
            if (mine && !message.deleted)
              ListTile(
                key: const Key('edit-message-option'),
                leading: const Icon(Icons.edit_outlined),
                title: const Text('Editar mensaje'),
                onTap: () => Navigator.pop(context, 'edit'),
              ),
            if (message.canViewHistory && message.editedAt != null)
              ListTile(
                key: const Key('message-history-option'),
                leading: const Icon(Icons.history),
                title: const Text('Versiones anteriores'),
                onTap: () => Navigator.pop(context, 'history'),
              ),
            if (canDelete)
              ListTile(
                key: const Key('delete-message-option'),
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
    } else if (action == 'edit') {
      final repository = ref.read(messagingRepositoryProvider);
      final cambiado = await editarMensaje(context, message, (texto) async {
        await repository.edit(
          profile,
          message,
          texto,
          internal: widget.internal,
        );
      });
      if (!mounted || !cambiado) return;
      if (_replyingTo?.id == message.id) setState(() => _replyingTo = null);
      if (widget.internal) {
        ref.invalidate(internalMessagesProvider(widget.conversationId));
        ref.invalidate(internalThreadsProvider);
      } else {
        ref.invalidate(messagesProvider(widget.conversationId));
        ref.invalidate(conversationsProvider);
      }
    } else if (action == 'history') {
      await verHistorialMensaje(
        context,
        () => ref
            .read(messagingRepositoryProvider)
            .messageHistory(message.id, internal: widget.internal),
      );
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
    asyncMessages.whenData(_markReadWhenMessagesArrive);
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
            data: (messages) {
              _scrollToBottomWhenOpened(messages);
              _scrollToSentMessageWhenReady(messages);
              return Scrollbar(
                controller: _scroll,
                child: ListView.builder(
                  key: const Key('message-list'),
                  controller: _scroll,
                  reverse: true,
                  padding: const EdgeInsets.symmetric(vertical: 14),
                  itemCount: messages.length,
                  itemBuilder: (context, index) {
                    final message = messages[messages.length - 1 - index];
                    final mine = messageBelongsToProfile(message, profile);
                    return MessageBubble(
                      message: message,
                      mine: mine,
                      mostrarEstados:
                          profile.type == UserType.staff &&
                          profile.verEstadosMensajes,
                      isStaff: profile.type == UserType.staff,
                      baseUrl: ref
                          .read(apiClientProvider)
                          .dio
                          .options
                          .baseUrl
                          .replaceAll(RegExp(r'/api/v1/messaging/?$'), ''),
                      authToken:
                          ref.read(sessionProvider).valueOrNull?.token ?? '',
                      onReplyTap: message.replyTo == null
                          ? null
                          : () =>
                                _scrollToMessage(messages, message.replyTo!.id),
                      onAttachmentTap: _download,
                      allowStaffAttachmentDownload: widget.internal,
                      onAttachmentHistory: profile.type == UserType.staff
                          ? _showAttachmentHistory
                          : null,
                      onAttachmentWithdraw: profile.isAdmin
                          ? _withdrawAttachment
                          : null,
                      onVoiceLoad: _loadVoice,
                      onTap: message.deleted && !message.canViewHistory
                          ? null
                          : () => _messageActions(message, mine),
                      onLongPress: message.deleted && !message.canViewHistory
                          ? null
                          : () => _messageActions(message, mine),
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
                  if (_recording) ...[
                    IconButton(
                      key: const Key('cancel-voice-note'),
                      tooltip: 'Cancelar nota de voz',
                      onPressed: () => _stopVoiceRecording(send: false),
                      icon: const Icon(Icons.delete_outline),
                    ),
                    const Icon(Icons.fiber_manual_record, color: Colors.red),
                    const SizedBox(width: 6),
                    Expanded(
                      child: Text(
                        'Grabando ${_recordingTime()}',
                        style: const TextStyle(fontWeight: FontWeight.w600),
                      ),
                    ),
                    IconButton.filled(
                      key: const Key('send-voice-note'),
                      tooltip: 'Detener y enviar',
                      onPressed: () => _stopVoiceRecording(send: true),
                      icon: const Icon(Icons.send),
                    ),
                  ] else ...[
                    IconButton(
                      key: const Key('attach-files'),
                      onPressed: _sending ? null : _pickFiles,
                      icon: const Icon(Icons.attach_file),
                    ),
                    Expanded(
                      child: TextField(
                        key: const Key('message-composer'),
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
                        ),
                      ),
                    ),
                    IconButton(
                      key: const Key('record-voice-note'),
                      tooltip: 'Grabar nota de voz',
                      onPressed: _sending ? null : _startVoiceRecording,
                      icon: const Icon(Icons.mic_none),
                    ),
                    const SizedBox(width: 4),
                    IconButton.filled(
                      key: const Key('send-message'),
                      onPressed: _sending
                          ? null
                          : () => _send(keepComposerFocus: true),
                      icon: _sending
                          ? const SizedBox.square(
                              dimension: 18,
                              child: CircularProgressIndicator(strokeWidth: 2),
                            )
                          : const Icon(Icons.send),
                    ),
                  ],
                ],
              ),
            ),
          ),
        ),
      ],
    );
  }
}

final class _VoicePlatformFile extends PlatformFile {
  _VoicePlatformFile({required this.name, required Uint8List bytes})
    : _bytes = bytes;

  @override
  final String name;
  final Uint8List _bytes;

  @override
  Uri get uri => Uri.dataFromBytes(_bytes);

  @override
  Future<int> length() async => _bytes.length;

  @override
  Future<Uint8List> readAsBytes() async => _bytes;

  @override
  Stream<Uint8List> readAsByteStream() => Stream.value(_bytes);

  @override
  dynamic noSuchMethod(Invocation invocation) => super.noSuchMethod(invocation);
}

bool messageBelongsToProfile(Message message, UserProfile profile) =>
    message.authorType == profile.type.name && message.authorId == profile.id;

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
              if (current?.kind == 'direct')
                Text(
                  current!.counterpartOnline ? 'Activo' : 'Inactivo',
                  style: Theme.of(context).textTheme.bodySmall?.copyWith(
                    color: current.counterpartOnline
                        ? Colors.green.shade700
                        : Theme.of(context).colorScheme.outline,
                  ),
                ),
            ],
          ),
        ),
      ],
    );
  }
}
