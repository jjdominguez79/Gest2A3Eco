import 'dart:convert';

import 'package:flutter_secure_storage/flutter_secure_storage.dart';

import '../../features/auth/domain/user_profile.dart';

class SessionStorage {
  SessionStorage([FlutterSecureStorage? storage])
    : _storage = storage ?? const FlutterSecureStorage();

  static const _key = 'gestinem.auth.session.v1';
  final FlutterSecureStorage _storage;

  Future<AuthSession?> read() async {
    final value = await _storage.read(key: _key);
    if (value == null || value.isEmpty) return null;
    try {
      return AuthSession.fromJson(jsonDecode(value) as Map<String, dynamic>);
    } catch (_) {
      await clear();
      return null;
    }
  }

  Future<void> write(AuthSession session) =>
      _storage.write(key: _key, value: jsonEncode(session.toJson()));

  Future<void> clear() => _storage.delete(key: _key);
}
