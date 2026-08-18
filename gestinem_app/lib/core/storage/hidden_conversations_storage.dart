import 'dart:convert';

import 'package:flutter_secure_storage/flutter_secure_storage.dart';

class HiddenConversationsStorage {
  HiddenConversationsStorage([FlutterSecureStorage? storage])
    : _storage = storage ?? const FlutterSecureStorage();

  final FlutterSecureStorage _storage;

  String _key(String staffId) =>
      'gestinem.messaging.hidden.${Uri.encodeComponent(staffId)}.v1';

  Future<Map<String, DateTime>> read(String staffId) async {
    final value = await _storage.read(key: _key(staffId));
    if (value == null || value.isEmpty) return {};
    try {
      final decoded = jsonDecode(value) as Map<String, dynamic>;
      return decoded.map(
        (code, timestamp) =>
            MapEntry(code, DateTime.parse(timestamp as String)),
      );
    } catch (_) {
      await _storage.delete(key: _key(staffId));
      return {};
    }
  }

  Future<void> hide(
    String staffId,
    String companyCode,
    DateTime updatedAt,
  ) async {
    final hidden = await read(staffId);
    hidden[companyCode] = updatedAt.toUtc();
    await _storage.write(
      key: _key(staffId),
      value: jsonEncode(
        hidden.map((code, date) => MapEntry(code, date.toIso8601String())),
      ),
    );
  }
}
