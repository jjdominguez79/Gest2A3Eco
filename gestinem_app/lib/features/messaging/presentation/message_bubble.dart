import 'package:flutter/material.dart';

import '../domain/message.dart';

class MessageBubble extends StatelessWidget {
  const MessageBubble({
    super.key,
    required this.message,
    required this.mine,
    this.baseUrl = '',
    this.showAuthor = true,
    this.onReplyTap,
    this.onAttachmentTap,
    this.onLongPress,
  });

  final Message message;
  final bool mine;
  final String baseUrl;
  final bool showAuthor;
  final VoidCallback? onReplyTap;
  final void Function(Attachment attachment)? onAttachmentTap;
  final VoidCallback? onLongPress;

  Widget _avatar() {
    if (message.authorAvatarUrl.isNotEmpty) {
      return CircleAvatar(
        radius: 16,
        backgroundImage: NetworkImage('$baseUrl${message.authorAvatarUrl}'),
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
    final bubbleColor = mine ? colors.primaryContainer : colors.surfaceContainerLow;
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
        mainAxisAlignment:
            mine ? MainAxisAlignment.end : MainAxisAlignment.start,
        children: [
          if (!mine) ...[_avatar(), const SizedBox(width: 6)],
          Flexible(
            child: GestureDetector(
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
                    if (!mine && showAuthor)
                      Text(
                        message.authorName,
                        style: TextStyle(
                          fontSize: 12,
                          fontWeight: FontWeight.w700,
                          color: colors.primary,
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
                            color: colors.surfaceContainerHighest
                                .withValues(alpha: .6),
                            border: Border(
                              left: BorderSide(
                                  color: colors.secondary, width: 3),
                            ),
                            borderRadius:
                                const BorderRadius.all(Radius.circular(4)),
                          ),
                          child: Column(
                            crossAxisAlignment: CrossAxisAlignment.start,
                            children: [
                              Text(
                                message.replyTo!.authorName,
                                style: const TextStyle(
                                    fontWeight: FontWeight.w600,
                                    fontSize: 11),
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
                                fontStyle: FontStyle.italic, fontSize: 13),
                          ),
                        ],
                      )
                    else if (message.body.isNotEmpty)
                      Text(message.body),
                    for (final att in message.attachments)
                      TextButton.icon(
                        onPressed: () => onAttachmentTap?.call(att),
                        icon: const Icon(Icons.attach_file, size: 16),
                        label: Text(
                          att.name,
                          overflow: TextOverflow.ellipsis,
                          style: const TextStyle(fontSize: 13),
                        ),
                        style: TextButton.styleFrom(
                          padding: EdgeInsets.zero,
                          minimumSize: Size.zero,
                        ),
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
