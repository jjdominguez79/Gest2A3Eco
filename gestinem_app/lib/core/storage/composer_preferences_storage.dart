import 'package:flutter_secure_storage/flutter_secure_storage.dart';

class ComposerPreferencesStorage {
  ComposerPreferencesStorage([FlutterSecureStorage? storage])
    : _storage = storage ?? const FlutterSecureStorage();

  final FlutterSecureStorage _storage;

  String _key(String userKey) =>
      'gestinem.messaging.send_with_enter.${Uri.encodeComponent(userKey)}.v1';

  Future<bool> readSendWithEnter(String userKey) async =>
      await _storage.read(key: _key(userKey)) == 'true';

  Future<void> writeSendWithEnter(String userKey, bool enabled) =>
      _storage.write(key: _key(userKey), value: enabled.toString());
}
