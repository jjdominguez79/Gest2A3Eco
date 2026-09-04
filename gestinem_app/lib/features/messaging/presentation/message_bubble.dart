import 'dart:async';
import 'dart:typed_data';

import 'package:audioplayers/audioplayers.dart';
import 'package:flutter/material.dart';

import '../../../core/widgets/authenticated_avatar.dart';
import '../domain/message.dart';

/// Tarjeta documental de un adjunto.
///
/// - [isStaff]: si es true, muestra estado de trazabilidad (no permite descargar).
/// - [onDownload]: solo se invoca para el cliente cuando el adjunto esta disponible.
class AttachmentCard extends StatelessWidget {
  const AttachmentCard({
    super.key,
    required this.attachment,
    required this.isStaff,
    this.onDownload,
    this.onShowHistory,
    this.onWithdraw,
    this.staffCanDownload = false,
  });

  final Attachment attachment;
  final bool isStaff;
  final VoidCallback? onDownload;
  final VoidCallback? onShowHistory;
  final VoidCallback? onWithdraw;
  final bool staffCanDownload;

  String _statusLabel() {
    switch (attachment.status) {
      case 'guardado_por_asesoria':
        return 'Guardado por la asesoria';
      case 'recibido_por_gestinem':
        return 'Recibido por Gestinem';
      case 'retirado':
        return 'Documento retirado por el despacho';
      case 'caducado':
        return 'Documento caducado';
      case 'disponible':
        return attachment.expiresAt != null
            ? 'Disponible hasta ${_fmtDate(attachment.expiresAt!)}'
            : 'Disponible';
      default:
        return attachment.status;
    }
  }

  String _fmtDate(DateTime dt) =>
      '${dt.day.toString().padLeft(2, '0')}/${dt.month.toString().padLeft(2, '0')}/${dt.year}';

  String _fmtSize(int bytes) {
    if (bytes >= 1048576) {
      return '${(bytes / 1048576).toStringAsFixed(1)}\u00a0MB';
    }
    if (bytes >= 1024) return '${(bytes / 1024).toStringAsFixed(1)}\u00a0KB';
    return '$bytes\u00a0B';
  }

  IconData _icon() {
    if (attachment.isWithdrawn) return Icons.remove_circle_outline;
    if (attachment.isExpired) return Icons.schedule;
    if (attachment.isIncoming) {
      return attachment.localConfirmed
          ? Icons.check_circle_outline
          : Icons.cloud_done_outlined;
    }
    return Icons.description_outlined;
  }

  Color _iconColor(ColorScheme colors) {
    if (attachment.isWithdrawn) return colors.error;
    if (attachment.isExpired) return colors.outline;
    if (attachment.localConfirmed ||
        attachment.status == 'guardado_por_asesoria') {
      return colors.primary;
    }
    return colors.secondary;
  }

  @override
  Widget build(BuildContext context) {
    final colors = Theme.of(context).colorScheme;
    final canDownload = attachment.available && (!isStaff || staffCanDownload);

    return Container(
      key: Key('attachment-card-${attachment.id}'),
      margin: const EdgeInsets.only(top: 6),
      padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 8),
      decoration: BoxDecoration(
        color: colors.surfaceContainerHighest.withValues(alpha: .55),
        borderRadius: const BorderRadius.all(Radius.circular(8)),
        border: Border.all(color: colors.outlineVariant),
      ),
      child: Row(
        children: [
          Icon(_icon(), size: 20, color: _iconColor(colors)),
          const SizedBox(width: 8),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  attachment.name,
                  overflow: TextOverflow.ellipsis,
                  style: const TextStyle(
                    fontSize: 13,
                    fontWeight: FontWeight.w500,
                  ),
                ),
                Text(
                  '${_fmtSize(attachment.size)} \u00b7 ${_statusLabel()}',
                  style: TextStyle(
                    fontSize: 11,
                    color: colors.onSurfaceVariant,
                  ),
                ),
                if (isStaff &&
                    !attachment.isIncoming &&
                    attachment.completedDownloadCount != null)
                  _StaffDownloadSummary(attachment: attachment),
                if (attachment.isWithdrawn &&
                    (attachment.withdrawalReason?.isNotEmpty ?? false))
                  Text(
                    'Motivo: ${attachment.withdrawalReason}',
                    style: TextStyle(fontSize: 11, color: colors.error),
                  ),
              ],
            ),
          ),
          if (canDownload)
            IconButton(
              key: Key('download-${attachment.id}'),
              icon: const Icon(Icons.download_outlined, size: 20),
              tooltip: 'Descargar',
              onPressed: onDownload,
            ),
          if (isStaff && !attachment.isIncoming && onShowHistory != null)
            IconButton(
              key: Key('download-history-${attachment.id}'),
              icon: const Icon(Icons.history, size: 20),
              tooltip: 'Ver historial de descargas',
              onPressed: onShowHistory,
            ),
          if (isStaff &&
              !attachment.isIncoming &&
              !attachment.isWithdrawn &&
              onWithdraw != null)
            IconButton(
              key: Key('withdraw-${attachment.id}'),
              icon: Icon(
                Icons.remove_circle_outline,
                size: 20,
                color: colors.error,
              ),
              tooltip: 'Retirar documento',
              onPressed: onWithdraw,
            ),
        ],
      ),
    );
  }
}

class _StaffDownloadSummary extends StatelessWidget {
  const _StaffDownloadSummary({required this.attachment});
  final Attachment attachment;

  String _fmt(DateTime? dt) {
    if (dt == null) return '\u2014';
    return '${dt.day.toString().padLeft(2, '0')}/${dt.month.toString().padLeft(2, '0')} '
        '${dt.hour.toString().padLeft(2, '0')}:${dt.minute.toString().padLeft(2, '0')}';
  }

  @override
  Widget build(BuildContext context) {
    final colors = Theme.of(context).colorScheme;
    final count = attachment.completedDownloadCount ?? 0;
    if (count == 0) {
      return Text(
        'Pendiente de descarga',
        style: TextStyle(fontSize: 11, color: colors.tertiary),
      );
    }
    final parts = <String>[
      'Descargas: $count',
      if (attachment.firstDownloadedAt != null)
        'Primera: ${_fmt(attachment.firstDownloadedAt)}',
      if (attachment.lastDownloadedAt != null)
        '\u00daltima: ${_fmt(attachment.lastDownloadedAt)}',
      if (attachment.lastClientName != null)
        'Por: ${attachment.lastClientName}',
    ];
    return Text(
      parts.join(' \u00b7 '),
      style: TextStyle(fontSize: 11, color: colors.onSurfaceVariant),
    );
  }
}

class VoiceNoteCard extends StatefulWidget {
  const VoiceNoteCard({
    super.key,
    required this.attachment,
    required this.loadAudio,
  });

  final Attachment attachment;
  final Future<Uint8List> Function() loadAudio;

  @override
  State<VoiceNoteCard> createState() => _VoiceNoteCardState();
}

class _VoiceNoteCardState extends State<VoiceNoteCard> {
  final AudioPlayer _player = AudioPlayer();
  final List<StreamSubscription<dynamic>> _subscriptions = [];
  Duration _duration = Duration.zero;
  Duration _position = Duration.zero;
  bool _loading = false;
  bool _playing = false;
  String? _error;

  @override
  void initState() {
    super.initState();
    _subscriptions.add(
      _player.onDurationChanged.listen((value) {
        if (mounted) setState(() => _duration = value);
      }),
    );
    _subscriptions.add(
      _player.onPositionChanged.listen((value) {
        if (mounted) setState(() => _position = value);
      }),
    );
    _subscriptions.add(
      _player.onPlayerStateChanged.listen((value) {
        if (!mounted) return;
        setState(() {
          _playing = value == PlayerState.playing;
          if (value == PlayerState.completed) _position = Duration.zero;
        });
      }),
    );
  }

  @override
  void dispose() {
    for (final subscription in _subscriptions) {
      unawaited(subscription.cancel());
    }
    unawaited(_player.dispose());
    super.dispose();
  }

  Future<void> _toggle() async {
    if (_playing) {
      await _player.pause();
      return;
    }
    setState(() {
      _loading = true;
      _error = null;
    });
    try {
      if (_player.state == PlayerState.paused) {
        await _player.resume();
      } else {
        final bytes = await widget.loadAudio();
        await _player.play(
          BytesSource(bytes, mimeType: widget.attachment.contentType),
        );
      }
    } catch (_) {
      if (mounted) setState(() => _error = 'No se pudo reproducir');
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  String _time(Duration value) {
    final minutes = value.inMinutes.toString().padLeft(2, '0');
    final seconds = (value.inSeconds % 60).toString().padLeft(2, '0');
    return '$minutes:$seconds';
  }

  @override
  Widget build(BuildContext context) {
    final colors = Theme.of(context).colorScheme;
    final max = _duration.inMilliseconds > 0
        ? _duration.inMilliseconds.toDouble()
        : 1.0;
    final value = _position.inMilliseconds.clamp(0, max.toInt()).toDouble();
    return Container(
      key: Key('voice-note-${widget.attachment.id}'),
      constraints: const BoxConstraints(minWidth: 230),
      margin: const EdgeInsets.only(top: 6),
      padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 4),
      decoration: BoxDecoration(
        color: colors.surfaceContainerHighest.withValues(alpha: .55),
        borderRadius: const BorderRadius.all(Radius.circular(20)),
      ),
      child: Row(
        children: [
          IconButton.filledTonal(
            key: Key('play-voice-${widget.attachment.id}'),
            tooltip: _playing ? 'Pausar nota de voz' : 'Reproducir nota de voz',
            onPressed: _loading ? null : _toggle,
            icon: _loading
                ? const SizedBox.square(
                    dimension: 18,
                    child: CircularProgressIndicator(strokeWidth: 2),
                  )
                : Icon(_playing ? Icons.pause : Icons.play_arrow),
          ),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Slider(
                  value: value,
                  max: max,
                  onChanged: _duration == Duration.zero
                      ? null
                      : (next) =>
                            _player.seek(Duration(milliseconds: next.round())),
                ),
                Text(
                  _error ??
                      '${_time(_position)} / ${_duration == Duration.zero ? '--:--' : _time(_duration)}',
                  style: TextStyle(
                    fontSize: 11,
                    color: _error == null
                        ? colors.onSurfaceVariant
                        : colors.error,
                  ),
                ),
              ],
            ),
          ),
          const Icon(Icons.mic, size: 18),
        ],
      ),
    );
  }
}

class MessageBubble extends StatelessWidget {
  const MessageBubble({
    super.key,
    required this.message,
    required this.mine,
    this.baseUrl = '',
    this.authToken = '',
    this.showAuthor = true,
    this.isStaff = false,
    this.allowStaffAttachmentDownload = false,
    this.onReplyTap,
    this.onAttachmentTap,
    this.onAttachmentHistory,
    this.onAttachmentWithdraw,
    this.onVoiceLoad,
    this.onTap,
    this.onLongPress,
  });

  final Message message;
  final bool mine;
  final String baseUrl;
  final String authToken;
  final bool showAuthor;

  /// True cuando el visor es personal del despacho (no cliente)
  final bool isStaff;
  final bool allowStaffAttachmentDownload;
  final VoidCallback? onReplyTap;

  /// Para cliente: se invoca al pulsar Descargar en un adjunto disponible.
  /// Para personal: no se invoca (las tarjetas son informativas).
  final void Function(Attachment attachment)? onAttachmentTap;
  final void Function(Attachment attachment)? onAttachmentHistory;
  final void Function(Attachment attachment)? onAttachmentWithdraw;
  final Future<Uint8List> Function(Attachment attachment)? onVoiceLoad;
  final VoidCallback? onTap;
  final VoidCallback? onLongPress;

  Widget _avatar() {
    if (message.authorAvatarUrl.isNotEmpty) {
      return AuthenticatedAvatar(
        radius: 16,
        baseUrl: baseUrl,
        authToken: authToken,
        imagePath: message.authorAvatarUrl,
        fallbackText: _initials(message.authorName),
        cacheVersion: message.authorId,
      );
    }
    final initials = message.authorName.isEmpty
        ? '?'
        : message.authorName
              .split(' ')
              .take(2)
              .map((w) => w.isEmpty ? '' : w[0])
              .join();
    return CircleAvatar(
      radius: 16,
      child: Text(initials.toUpperCase(), style: const TextStyle(fontSize: 12)),
    );
  }

  String _initials(String value) => value.isEmpty
      ? '?'
      : value
            .split(' ')
            .where((word) => word.isNotEmpty)
            .take(2)
            .map((word) => word[0])
            .join()
            .toUpperCase();

  String _timeLabel(DateTime dt) {
    final now = DateTime.now();
    final h = dt.hour.toString().padLeft(2, '0');
    final m = dt.minute.toString().padLeft(2, '0');
    if (dt.year == now.year && dt.month == now.month && dt.day == now.day) {
      return '$h:$m';
    }
    return '${dt.day.toString().padLeft(2, '0')}/${dt.month.toString().padLeft(2, '0')} $h:$m';
  }

  @override
  Widget build(BuildContext context) {
    final colors = Theme.of(context).colorScheme;
    final bubbleColor = mine
        ? colors.primaryContainer
        : colors.surfaceContainerLow;
    final align = mine ? CrossAxisAlignment.end : CrossAxisAlignment.start;

    return Padding(
      padding: EdgeInsets.only(
        left: mine ? 64 : 8,
        right: mine ? 8 : 64,
        top: 3,
        bottom: 3,
      ),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.end,
        mainAxisAlignment: mine
            ? MainAxisAlignment.end
            : MainAxisAlignment.start,
        children: [
          if (!mine) ...[_avatar(), const SizedBox(width: 6)],
          Flexible(
            child: GestureDetector(
              onTap: onTap,
              onLongPress: onLongPress,
              child: Container(
                key: Key('message-${message.id}'),
                padding: const EdgeInsets.all(10),
                decoration: BoxDecoration(
                  color: bubbleColor,
                  borderRadius: BorderRadius.only(
                    topLeft: const Radius.circular(14),
                    topRight: const Radius.circular(14),
                    bottomLeft: mine
                        ? const Radius.circular(14)
                        : const Radius.circular(3),
                    bottomRight: mine
                        ? const Radius.circular(3)
                        : const Radius.circular(14),
                  ),
                ),
                child: Column(
                  crossAxisAlignment: align,
                  children: [
                    if (showAuthor)
                      Text(
                        mine
                            ? 'T\u00fa'
                            : (message.authorName.trim().isEmpty
                                  ? 'Emisor desconocido'
                                  : message.authorName),
                        style: TextStyle(
                          fontSize: 12,
                          fontWeight: FontWeight.w700,
                          color: mine
                              ? colors.onPrimaryContainer
                              : colors.primary,
                        ),
                      ),
                    if (message.replyTo != null) ...[
                      const SizedBox(height: 4),
                      InkWell(
                        key: const Key('reply-reference'),
                        onTap: onReplyTap,
                        child: Container(
                          width: double.infinity,
                          padding: const EdgeInsets.all(6),
                          decoration: BoxDecoration(
                            color: colors.surfaceContainerHighest.withValues(
                              alpha: .6,
                            ),
                            border: Border(
                              left: BorderSide(
                                color: colors.secondary,
                                width: 3,
                              ),
                            ),
                            borderRadius: const BorderRadius.all(
                              Radius.circular(4),
                            ),
                          ),
                          child: Column(
                            crossAxisAlignment: CrossAxisAlignment.start,
                            children: [
                              Text(
                                message.replyTo!.authorName,
                                style: const TextStyle(
                                  fontWeight: FontWeight.w600,
                                  fontSize: 11,
                                ),
                              ),
                              Text(
                                message.replyTo!.bodyFragment,
                                maxLines: 2,
                                overflow: TextOverflow.ellipsis,
                                style: const TextStyle(fontSize: 12),
                              ),
                            ],
                          ),
                        ),
                      ),
                    ],
                    const SizedBox(height: 4),
                    if (message.deleted)
                      const Row(
                        key: Key('deleted-message'),
                        mainAxisSize: MainAxisSize.min,
                        children: [
                          Icon(Icons.block, size: 15),
                          SizedBox(width: 4),
                          Text(
                            'Mensaje eliminado',
                            style: TextStyle(
                              fontStyle: FontStyle.italic,
                              fontSize: 13,
                            ),
                          ),
                        ],
                      )
                    else if (message.body.isNotEmpty)
                      Text(message.body),
                    for (final att in message.attachments)
                      if (att.isVoiceNote && onVoiceLoad != null)
                        VoiceNoteCard(
                          attachment: att,
                          loadAudio: () => onVoiceLoad!(att),
                        )
                      else
                        AttachmentCard(
                          attachment: att,
                          isStaff: isStaff,
                          staffCanDownload: allowStaffAttachmentDownload,
                          onDownload:
                              (att.available &&
                                  (!isStaff || allowStaffAttachmentDownload))
                              ? () => onAttachmentTap?.call(att)
                              : null,
                          onShowHistory:
                              isStaff &&
                                  !att.isIncoming &&
                                  onAttachmentHistory != null
                              ? () => onAttachmentHistory?.call(att)
                              : null,
                          onWithdraw:
                              isStaff &&
                                  !att.isIncoming &&
                                  !att.isWithdrawn &&
                                  onAttachmentWithdraw != null
                              ? () => onAttachmentWithdraw?.call(att)
                              : null,
                        ),
                    Align(
                      alignment: mine
                          ? Alignment.bottomRight
                          : Alignment.bottomLeft,
                      child: Text(
                        _timeLabel(message.createdAt),
                        style: Theme.of(context).textTheme.labelSmall?.copyWith(
                          color: colors.onSurface.withValues(alpha: .55),
                        ),
                      ),
                    ),
                  ],
                ),
              ),
            ),
          ),
          if (mine) const SizedBox(width: 6),
        ],
      ),
    );
  }
}
