import 'package:flutter_test/flutter_test.dart';
import 'package:gestinem/core/deep_links/deep_link_controller.dart';

void main() {
  test('convierte invitacion Flutter en ruta interna', () {
    final route = routeForDeepLink(
      Uri.parse('es.gestinem.app://auth/invite?token=abc-123'),
    );

    expect(route, '/accept-invite?token=abc-123');
  });

  test('convierte recuperacion Flutter en ruta interna', () {
    final route = routeForDeepLink(
      Uri.parse('es.gestinem.app://auth/reset?token=abc%2B123'),
    );

    expect(route, '/reset-password?token=abc%2B123');
  });

  test('ignora enlaces ajenos', () {
    expect(routeForDeepLink(Uri.parse('https://example.test/invite')), isNull);
    expect(
      routeForDeepLink(Uri.parse('es.gestinem.app://auth/callback?code=abc')),
      isNull,
    );
  });
}
