import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:gestinem/core/storage/hidden_conversations_storage.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  setUp(() => FlutterSecureStorage.setMockInitialValues({}));

  test('conserva conversaciones ocultas por empleado', () async {
    final storage = HiddenConversationsStorage();
    final timestamp = DateTime.utc(2026, 8, 18, 17, 30);

    await storage.hide('admin', 'E00006', timestamp);

    expect(await storage.read('admin'), {'E00006': timestamp});
    expect(await storage.read('otro-empleado'), isEmpty);
  });
}
