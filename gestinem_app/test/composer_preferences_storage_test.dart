import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:gestinem/core/storage/composer_preferences_storage.dart';

void main() {
  setUp(() => FlutterSecureStorage.setMockInitialValues({}));

  test('Intro no envia hasta que el usuario activa la preferencia', () async {
    final storage = ComposerPreferencesStorage();

    expect(await storage.readSendWithEnter('client.client-1'), isFalse);
    await storage.writeSendWithEnter('client.client-1', true);
    expect(await storage.readSendWithEnter('client.client-1'), isTrue);
    expect(await storage.readSendWithEnter('staff.client-1'), isFalse);
  });
}
