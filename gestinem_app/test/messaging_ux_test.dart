import 'package:flutter_test/flutter_test.dart';
import 'package:gestinem/features/messaging/domain/conversation.dart';
import 'package:gestinem/features/messaging/domain/message.dart';

void main() {
  group('groupConversationsByClient', () {
    test('returns empty list for empty input', () {
      expect(groupConversationsByClient([]), isEmpty);
    });

    test('groups conversations by company code', () {
      final convs = [
        _makeConv('E001', 'Empresa A', 'laboral'),
        _makeConv('E001', 'Empresa A', 'fiscal'),
        _makeConv('E002', 'Empresa B', 'fiscal'),
      ];
      final groups = groupConversationsByClient(convs);
      expect(groups.length, 2);
      expect(
        groups.firstWhere((g) => g.companyCode == 'E001').conversations.length,
        2,
      );
      expect(
        groups.firstWhere((g) => g.companyCode == 'E002').conversations.length,
        1,
      );
    });

    test('sums unread counts correctly', () {
      final convs = [
        _makeConv('E001', 'Empresa A', 'laboral', unread: 3),
        _makeConv('E001', 'Empresa A', 'fiscal', unread: 2),
      ];
      final groups = groupConversationsByClient(convs);
      expect(groups.first.totalUnread, 5);
    });

    test('displayName uses companyName when available', () {
      final convs = [_makeConv('E001', 'Mi Empresa', 'fiscal')];
      final groups = groupConversationsByClient(convs);
      expect(groups.first.displayName, 'Mi Empresa');
    });

    test('displayName falls back to companyCode', () {
      final convs = [_makeConv('E001', '', 'fiscal')];
      final groups = groupConversationsByClient(convs);
      expect(groups.first.displayName, 'E001');
    });

    test('single channel group has one conversation', () {
      final convs = [_makeConv('E003', 'Empresa C', 'laboral')];
      final groups = groupConversationsByClient(convs);
      expect(groups.length, 1);
      expect(groups.first.conversations.length, 1);
    });

    test('sorts groups by updatedAt descending', () {
      final now = DateTime.now();
      final convs = [
        _makeConv(
          'E001',
          'Empresa A',
          'fiscal',
          updatedAt: now.subtract(const Duration(hours: 2)),
        ),
        _makeConv('E002', 'Empresa B', 'fiscal', updatedAt: now),
      ];
      final groups = groupConversationsByClient(convs);
      expect(groups.first.companyCode, 'E002');
    });
  });

  group('Message.fromJson', () {
    test('parses author_avatar_url', () {
      final json = {
        'id': '1',
        'conversation_id': 'c1',
        'author_type': 'staff',
        'author_id': 'u1',
        'author_name': 'Maria',
        'body': 'Hola',
        'created_at': '2026-01-01T10:00:00Z',
        'deleted': false,
        'author_avatar_url': '/api/v1/messaging/staff/avatars/u1',
      };
      final msg = Message.fromJson(json);
      expect(msg.authorAvatarUrl, '/api/v1/messaging/staff/avatars/u1');
    });

    test('defaults author_avatar_url to empty string', () {
      final json = {
        'id': '1',
        'conversation_id': 'c1',
        'author_type': 'client',
        'author_id': 'u1',
        'author_name': 'Cliente',
        'body': 'Mensaje',
        'created_at': '2026-01-01T10:00:00Z',
        'deleted': false,
      };
      final msg = Message.fromJson(json);
      expect(msg.authorAvatarUrl, '');
    });

    test('parses author_avatar_url as empty when null in json', () {
      final json = {
        'id': '2',
        'conversation_id': 'c2',
        'author_type': 'staff',
        'author_id': 'u2',
        'author_name': 'Pedro',
        'body': 'Test',
        'created_at': '2026-06-01T12:00:00Z',
        'deleted': false,
        'author_avatar_url': null,
      };
      final msg = Message.fromJson(json);
      expect(msg.authorAvatarUrl, '');
    });
  });

  group('ClientGroup', () {
    test('displayName uses companyName if not empty', () {
      final group = ClientGroup(
        companyCode: 'E001',
        companyName: 'Mi Empresa',
        conversations: [],
        totalUnread: 0,
      );
      expect(group.displayName, 'Mi Empresa');
    });

    test('displayName falls back to companyCode when companyName is empty', () {
      final group = ClientGroup(
        companyCode: 'E001',
        companyName: '',
        conversations: [],
        totalUnread: 0,
      );
      expect(group.displayName, 'E001');
    });

    test('totalUnread accumulates across conversations', () {
      final convs = [
        _makeConv('E001', 'A', 'laboral', unread: 5),
        _makeConv('E001', 'A', 'fiscal', unread: 3),
      ];
      final groups = groupConversationsByClient(convs);
      expect(groups.first.totalUnread, 8);
    });
  });

  group('UnifiedConversation routing', () {
    test('client unread total from multiple conversations', () {
      final convs = [
        _makeConv('E001', 'Mi Empresa', 'laboral', unread: 2),
        _makeConv('E001', 'Mi Empresa', 'fiscal', unread: 1),
        _makeConv('E001', 'Mi Empresa', 'private', unread: 0),
      ];
      // Los clientes NO usan groupConversationsByClient, pero verificamos
      // que todos los unreads estan presentes en la lista original
      final totalUnread = convs.fold(0, (s, c) => s + c.unreadCount);
      expect(totalUnread, 3);
    });

    test(
      'groupConversationsByClient groups same client into one group with all channels',
      () {
        final convs = [
          _makeConv('E001', 'Empresa', 'laboral', unread: 1),
          _makeConv('E001', 'Empresa', 'fiscal', unread: 2),
          _makeConv('E001', 'Empresa', 'private', unread: 0),
        ];
        final groups = groupConversationsByClient(convs);
        expect(groups.length, 1, reason: 'Staff ve 1 grupo por cliente');
        expect(groups.first.conversations.length, 3);
        expect(groups.first.totalUnread, 3);
      },
    );
  });
}

Conversation _makeConv(
  String code,
  String name,
  String kind, {
  int unread = 0,
  DateTime? updatedAt,
}) {
  return Conversation(
    id: '${code}_$kind',
    companyCode: code,
    companyName: name,
    kind: kind,
    state: 'pendiente',
    unreadCount: unread,
    updatedAt: updatedAt ?? DateTime.now(),
  );
}
