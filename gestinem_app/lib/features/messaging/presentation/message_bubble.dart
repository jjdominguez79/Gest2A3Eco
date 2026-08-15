import 'package:flutter/material.dart';

import '../domain/message.dart';

class MessageBubble extends StatelessWidget {
  const MessageBubble({
    super.key,
    required this.message,
    required this.mine,
    this.onReplyTap,
    this.onAttachmentTap,
    this.onLongPress,
  });

  final Message message;
  final bool mine;
  final VoidCallback? onReplyTap;
  final void Function(Attachment attachment)? onAttachmentTap;
  final VoidCallback? onLongPress;

  @override
  Widget build(BuildContext context) {
    final colors = Theme.of(context).colorScheme;
    return Align(
      alignment: mine ? Alignment.centerRight : Alignment.centerLeft,
      child: GestureDetector(
        onLongPress: onLongPress,
        child: Container(
          key: Key('message-${message.id}'),
          constraints: const BoxConstraints(maxWidth: 560),
          margin: const EdgeInsets.symmetric(vertical: 5, horizontal: 12),
          padding: const EdgeInsets.all(12),
          decoration: BoxDecoration(
            color: mine ? colors.primaryContainer : Colors.white,
            borderRadius: BorderRadius.circular(14).copyWith(
              bottomRight: mine ? const Radius.circular(3) : null,
              bottomLeft: mine ? null : const Radius.circular(3),
            ),
            border: Border.all(color: colors.outlineVariant),
          ),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(message.authorName, style: TextStyle(fontSize: 12, fontWeight: FontWeight.w700, color: colors.primary)),
              if (message.replyTo != null) ...[
                const SizedBox(height: 6),
                InkWell(
                  key: const Key('reply-reference'),
                  onTap: onReplyTap,
                  child: Container(
                    width: double.infinity,
                    padding: const EdgeInsets.all(8),
                    decoration: BoxDecoration(
                      color: colors.surfaceContainerHighest.withValues(alpha: .65),
                      border: Border(left: BorderSide(color: colors.secondary, width: 3)),
                    ),
                    child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                      Text(message.replyTo!.authorName, style: const TextStyle(fontWeight: FontWeight.w600, fontSize: 12)),
                      Text(message.replyTo!.bodyFragment, maxLines: 2, overflow: TextOverflow.ellipsis),
                    ]),
                  ),
                ),
              ],
              const SizedBox(height: 5),
              if (message.deleted)
                const Row(key: Key('deleted-message'), mainAxisSize: MainAxisSize.min, children: [
                  Icon(Icons.block, size: 16), SizedBox(width: 6), Text('Mensaje eliminado', style: TextStyle(fontStyle: FontStyle.italic)),
                ])
              else if (message.body.isNotEmpty)
                Text(message.body),
              for (final attachment in message.attachments)
                TextButton.icon(
                  onPressed: () => onAttachmentTap?.call(attachment),
                  icon: const Icon(Icons.attach_file),
                  label: Text(attachment.name, overflow: TextOverflow.ellipsis),
                ),
              Align(
                alignment: Alignment.bottomRight,
                child: Text(
                  '${message.createdAt.day.toString().padLeft(2, '0')}/${message.createdAt.month.toString().padLeft(2, '0')} ${message.createdAt.hour.toString().padLeft(2, '0')}:${message.createdAt.minute.toString().padLeft(2, '0')}',
                  style: Theme.of(context).textTheme.labelSmall,
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}
