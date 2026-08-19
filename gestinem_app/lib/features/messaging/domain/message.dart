class Attachment {
  const Attachment({
    required this.id,
    required this.name,
    required this.contentType,
    required this.size,
    this.direction = 'outgoing',
    this.status = 'disponible',
    this.available = false,
    this.expiresAt,
    this.localConfirmed = false,
    this.withdrawnAt,
    this.withdrawnBy,
    this.withdrawalReason,
    this.sha256,
    this.completedDownloadCount,
    this.firstDownloadedAt,
    this.lastDownloadedAt,
    this.lastClientName,
  });

  factory Attachment.fromJson(Map<String, dynamic> json) => Attachment(
        id: json['id'] as String,
        name: json['name'] as String? ?? 'adjunto',
        contentType: json['content_type'] as String? ?? 'application/octet-stream',
        size: json['size'] as int? ?? 0,
        direction: json['direction'] as String? ?? 'outgoing',
        status: json['status'] as String? ?? 'disponible',
        available: json['available'] as bool? ?? false,
        expiresAt: json['expires_at'] != null
            ? DateTime.parse(json['expires_at'] as String).toLocal()
            : null,
        localConfirmed: json['local_confirmed'] as bool? ?? false,
        withdrawnAt: json['withdrawn_at'] != null
            ? DateTime.parse(json['withdrawn_at'] as String).toLocal()
            : null,
        withdrawnBy: json['withdrawn_by'] as String?,
        withdrawalReason: json['withdrawal_reason'] as String?,
        sha256: json['sha256'] as String?,
        completedDownloadCount: json['completed_download_count'] as int?,
        firstDownloadedAt: json['first_downloaded_at'] != null
            ? DateTime.parse(json['first_downloaded_at'] as String).toLocal()
            : null,
        lastDownloadedAt: json['last_downloaded_at'] != null
            ? DateTime.parse(json['last_downloaded_at'] as String).toLocal()
            : null,
        lastClientName: json['last_client_name'] as String?,
      );

  final String id;
  final String name;
  final String contentType;
  final int size;
  /// 'incoming' (cliente -> despacho) o 'outgoing' (despacho -> cliente)
  final String direction;
  /// 'disponible' | 'caducado' | 'retirado' | 'recibido_por_gestinem' | 'guardado_por_asesoria'
  final String status;
  /// Solo para cliente: true si el adjunto saliente aun puede descargarse
  final bool available;
  /// Fecha de caducidad (adjuntos salientes)
  final DateTime? expiresAt;
  /// Confirmado por el NAS (adjuntos entrantes)
  final bool localConfirmed;
  /// Cuando fue retirado (adjuntos salientes retirados)
  final DateTime? withdrawnAt;
  final String? withdrawnBy;
  final String? withdrawalReason;
  final String? sha256;
  // Resumen de descargas (solo para personal, adjuntos salientes)
  final int? completedDownloadCount;
  final DateTime? firstDownloadedAt;
  final DateTime? lastDownloadedAt;
  final String? lastClientName;

  bool get isIncoming => direction == 'incoming';
  bool get isWithdrawn => withdrawnAt != null;
  bool get isExpired => status == 'caducado';
}

class AttachmentDownload {
  const AttachmentDownload({
    required this.id,
    required this.clientId,
    required this.clientName,
    required this.downloadedAt,
    required this.completedAt,
    required this.ip,
    required this.userAgent,
    required this.sha256,
    required this.success,
  });

  factory AttachmentDownload.fromJson(Map<String, dynamic> json) =>
      AttachmentDownload(
        id: json['id'] as String? ?? '',
        clientId: json['client_id'] as String? ?? '',
        clientName: json['client_name'] as String? ?? '',
        downloadedAt: DateTime.parse(json['downloaded_at'] as String).toLocal(),
        completedAt: json['completed_at'] == null
            ? null
            : DateTime.parse(json['completed_at'] as String).toLocal(),
        ip: json['ip'] as String? ?? '',
        userAgent: json['user_agent'] as String? ?? '',
        sha256: json['sha256'] as String? ?? '',
        success: json['success'] as bool? ?? false,
      );

  final String id;
  final String clientId;
  final String clientName;
  final DateTime downloadedAt;
  final DateTime? completedAt;
  final String ip;
  final String userAgent;
  final String sha256;
  final bool success;
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
    this.hasAttachments = false,
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
        hasAttachments: json['has_attachments'] as bool? ?? false,
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
  /// True si el mensaje tiene o tuvo adjuntos (incluso si esta eliminado logicamente).
  /// Evita ofrecer la accion Eliminar en este tipo de mensajes.
  final bool hasAttachments;
  final ReplyReference? replyTo;
  final List<Attachment> attachments;
}
