import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:gestinem/features/messaging/presentation/selector_contacto_nativo.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  const canal = MethodChannel('flutter_native_contact_picker');

  tearDown(() {
    TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger
        .setMockMethodCallHandler(canal, null);
  });

  test('convierte el contacto elegido al formato del mensaje', () async {
    TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger
        .setMockMethodCallHandler(canal, (call) async {
          expect(call.method, 'selectPhoneNumber');
          return <String, Object>{
            'fullName': 'Ana Garcia',
            'phoneNumbers': <String>['600 111 222', '600 333 444'],
            'selectedPhoneNumber': '600 333 444',
          };
        });

    final contacto = await seleccionarContactoNativo();

    expect(contacto?.name, 'Ana Garcia');
    expect(contacto?.phone, '600 333 444');
    expect(contacto?.email, isEmpty);
    expect(contacto?.organization, isEmpty);
  });

  test('devuelve null si se cancela el selector', () async {
    TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger
        .setMockMethodCallHandler(canal, (_) async => null);

    expect(await seleccionarContactoNativo(), isNull);
  });
}
