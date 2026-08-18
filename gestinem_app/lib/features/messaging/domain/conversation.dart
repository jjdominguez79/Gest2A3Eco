import 'message.dart';

class ClientGroup {
  const ClientGroup({
    required this.companyCode,
    required this.companyName,
    required this.conversations,
    required this.totalUnread,
    this.lastMessage,
    this.updatedAt,
  });

  final String companyCode;
  final String companyName;
  final List<Conversation> conversations;
  final int totalUnread;
  final Message? lastMessage;
  final DateTime? updatedAt;

  String get displayName => companyName.isEmpty ? companyCode : companyName;
}

List<ClientGroup> groupConversationsByClient(List<Conversation> conversations) {
  final map = <String, List<Conversation>>{};
  for (final conv in conversations) {
    map.putIfAbsent(conv.companyCode, () => []).add(conv);
  }
  return map.entries.map((e) {
    final convs = e.value..sort((a, b) => b.updatedAt.compareTo(a.updatedAt));
    final totalUnread = convs.fold(0, (sum, c) => sum + c.unreadCount);
    Message? lastMsg;
    DateTime? lastUpdated;
    for (final c in convs) {
      if (lastUpdated == null || c.updatedAt.isAfter(lastUpdated)) {
        lastUpdated = c.updatedAt;
        lastMsg = c.lastMessage;
      }
    }
    return ClientGroup(
      companyCode: e.key,
      companyName: convs.first.companyName,
      conversations: convs,
      totalUnread: totalUnread,
      lastMessage: lastMsg,
      updatedAt: lastUpdated,
    );
  }).toList()..sort(
    (a, b) =>
        (b.updatedAt ?? DateTime(0)).compareTo(a.updatedAt ?? DateTime(0)),
  );
}

class Conversation {
  const Conversation({
    required this.id,
    required this.companyCode,
    required this.companyName,
    required this.kind,
    this.channelLabel = '',
    this.channelAvatarUrl = '',
    required this.state,
    required this.unreadCount,
    required this.updatedAt,
    this.lastMessage,
  });

  factory Conversation.fromJson(Map<String, dynamic> json) => Conversation(
    id: json['id'] as String,
    companyCode: json['company_code'] as String? ?? '',
    companyName: json['company_name'] as String? ?? '',
    kind: json['kind'] as String? ?? '',
    channelLabel: json['channel_label'] as String? ?? '',
    channelAvatarUrl: json['channel_avatar_url'] as String? ?? '',
    state: json['state'] as String? ?? 'pendiente',
    unreadCount: json['unread_count'] as int? ?? 0,
    updatedAt: DateTime.parse(json['updated_at'] as String).toLocal(),
    lastMessage: json['last_message'] is Map<String, dynamic>
        ? Message.fromJson(json['last_message'] as Map<String, dynamic>)
        : null,
  );

  final String id;
  final String companyCode;
  final String companyName;
  final String kind;
  final String channelLabel;
  final String channelAvatarUrl;
  final String state;
  final int unreadCount;
  final DateTime updatedAt;
  final Message? lastMessage;

  String get displayChannelLabel => channelLabel.isNotEmpty
      ? channelLabel
      : switch (kind) {
          'laboral' => 'LA',
          'fiscal' => 'CF',
          _ => 'DP',
        };

  String get title => companyName.isEmpty ? _channelLabel(kind) : companyName;

  static String _channelLabel(String value) => switch (value) {
    'laboral' => 'Laboral',
    'fiscal' => 'Contable / Fiscal',
    'private' => 'Directo',
    _ => value,
  };
}

class InternalThread {
  const InternalThread({
    required this.id,
    required this.kind,
    required this.channel,
    required this.title,
    required this.unreadCount,
  });

  factory InternalThread.fromJson(Map<String, dynamic> json) => InternalThread(
    id: json['id'] as String,
    kind: json['kind'] as String? ?? '',
    channel: json['channel'] as String? ?? '',
    title: json['title'] as String? ?? 'Chat interno',
    unreadCount: json['unread_count'] as int? ?? 0,
  );

  final String id;
  final String kind;
  final String channel;
  final String title;
  final int unreadCount;
}
