class Attachment {
  const Attachment({
    required this.id,
    required this.name,
    required this.contentType,
    required this.size,
  });

  factory Attachment.fromJson(Map<String, dynamic> json) => Attachment(
        id: json['id'] as String,
        name: json['name'] as String? ?? 'adjunto',
        contentType: json['content_type'] as String? ?? 'application/octet-stream',
        size: json['size'] as int? ?? 0,
      );

  final String id;
  final String name;
  final String contentType;
  final int size;
}

class ReplyReference {
  const ReplyReference({
    required this.id,
    required this.authorName,
    required this.bodyFragment,
    required this.deleted,
  });

  factory ReplyReference.fromJson(Map<String, dynamic> json) => ReplyReference(
        id: json['id'] as String,
        authorName: json['author_name'] as String? ?? '',
        bodyFragment: json['body_fragment'] as String? ?? '',
        deleted: json['deleted'] as bool? ?? false,
      );

  final String id;
  final String authorName;
  final String bodyFragment;
  final bool deleted;
}

class Message {
  const Message({
    required this.id,
    required this.conversationId,
    required this.authorType,
    required this.authorId,
    required this.authorName,
    required this.authorAvatarUrl,
    required this.body,
    required this.createdAt,
    required this.deleted,
    this.replyTo,
    this.attachments = const [],
  });

  factory Message.fromJson(Map<String, dynamic> json) => Message(
        id: json['id'] as String,
        conversationId: (json['conversation_id'] ?? json['thread_id']) as String,
        authorType: json['author_type'] as String? ?? 'staff',
        authorId: (json['author_id'] ?? '') as String,
        authorName: json['author_name'] as String? ?? '',
        authorAvatarUrl: json['author_avatar_url'] as String? ?? '',
        body: json['body'] as String? ?? '',
        createdAt: DateTime.parse(json['created_at'] as String).toLocal(),
        deleted: json['deleted'] as bool? ?? false,
        replyTo: json['reply_to'] is Map<String, dynamic>
            ? ReplyReference.fromJson(json['reply_to'] as Map<String, dynamic>)
            : null,
        attachments: (json['attachments'] as List<dynamic>? ?? const [])
            .map((item) => Attachment.fromJson(item as Map<String, dynamic>))
            .toList(growable: false),
      );

  final String id;
  final String conversationId;
  final String authorType;
  final String authorId;
  final String authorName;
  final String authorAvatarUrl;
  final String body;
  final DateTime createdAt;
  final bool deleted;
  final ReplyReference? replyTo;
  final List<Attachment> attachments;
}
