import 'package:flutter_test/flutter_test.dart';
import 'package:gestinem/core/sharing/android_share_receiver.dart';

void main() {
  group('SharedContent', () {
    test('convierte los archivos recibidos por el canal Android', () async {
      final content = SharedContent.fromPlatformPayload({
        'files': [
          {'name': 'factura.pdf', 'path': r'C:\cache\factura.pdf', 'size': 321},
        ],
      });

      expect(content.error, isNull);
      expect(content.files, hasLength(1));
      expect(content.files.single.name, 'factura.pdf');
      expect(await content.files.single.length(), 321);
      expect(content.files.single.path, contains('factura.pdf'));
    });

    test('ignora entradas incompletas y conserva el error nativo', () {
      final content = SharedContent.fromPlatformPayload({
        'files': [
          {'name': 'sin-ruta.pdf', 'size': 10},
        ],
        'error': 'Formato no admitido',
      });

      expect(content.files, isEmpty);
      expect(content.error, 'Formato no admitido');
    });

    test('rechaza una respuesta que no sea un mapa', () {
      final content = SharedContent.fromPlatformPayload('incorrecto');

      expect(content.files, isEmpty);
      expect(content.error, isNotEmpty);
    });
  });
}
