import 'dart:convert';
import 'dart:typed_data';

import 'package:dio/dio.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:gestinem/core/api/api_client.dart';
import 'package:gestinem/features/auth/domain/user_profile.dart';
import 'package:gestinem/features/auth/presentation/auth_controller.dart';
import 'package:gestinem/features/messaging/presentation/invitation_content_screen.dart';

import 'test_helpers.dart';

class _InvitationAdapter implements HttpClientAdapter {
  static const content = {
    'active': {
      'id': 'version-1',
      'version': 1,
      'status': 'published',
      'subject': 'Bienvenido a Gestinem',
      'intro_text': 'Hola {{nombre_cliente}},\n\nTexto inicial.',
      'closing_text': 'El enlace dura {{horas_caducidad}} horas.',
      'manual_name': 'Manual.pdf',
      'manual_size': 2048,
      'has_custom_manual': true,
      'manual_url': 'https://api.example.test/manual',
      'published_at': '2026-09-28T10:00:00Z',
    },
    'draft': null,
    'manual_url': 'https://api.example.test/manual',
    'allowed_variables': ['{{nombre_cliente}}', '{{horas_caducidad}}'],
  };

  @override
  Future<ResponseBody> fetch(
    RequestOptions options,
    Stream<Uint8List>? requestStream,
    Future<void>? cancelFuture,
  ) async {
    final payload = options.path.endsWith('/history') ? <Object>[] : content;
    return ResponseBody.fromString(
      jsonEncode(payload),
      200,
      headers: {
        Headers.contentTypeHeader: ['application/json'],
      },
    );
  }

  @override
  void close({bool force = false}) {}
}

void main() {
  testWidgets('administrador edita correo y ve el manual como enlace', (
    tester,
  ) async {
    await tester.binding.setSurfaceSize(const Size(1100, 900));
    addTearDown(() => tester.binding.setSurfaceSize(null));
    const profile = UserProfile(
      id: 'admin',
      name: 'Administrador',
      email: 'admin@gestinem.es',
      type: UserType.staff,
      staffRole: StaffRole.admin,
    );
    const session = AuthSession(token: 'staff-token', profile: profile);
    final api = ApiClient(
      dio: Dio(BaseOptions(baseUrl: 'https://example.test/api/v1/messaging'))
        ..httpClientAdapter = _InvitationAdapter(),
      tokenProvider: () => session.token,
    );

    await tester.pumpWidget(
      ProviderScope(
        overrides: [
          sessionProvider.overrideWith(
            (ref) => FakeSessionController(ref, session),
          ),
          apiClientProvider.overrideWithValue(api),
        ],
        child: const MaterialApp(home: InvitationContentScreen()),
      ),
    );
    await tester.pumpAndSettle();

    expect(find.text('Invitación de clientes'), findsOneWidget);
    expect(find.byKey(const Key('invitation-subject')), findsOneWidget);
    expect(find.text('Bienvenido a Gestinem'), findsOneWidget);
    expect(find.text('Enlaces protegidos'), findsOneWidget);
    expect(
      find.text('• Activar mi cuenta y acceder a Gestinem'),
      findsOneWidget,
    );
    expect(find.text('• Consultar el manual de Gestinem'), findsOneWidget);
    await tester.drag(find.byType(ListView), const Offset(0, -1100));
    await tester.pumpAndSettle();
    expect(find.byKey(const Key('upload-invitation-manual')), findsOneWidget);
    expect(find.textContaining('no se adjunta al correo'), findsOneWidget);
    await tester.drag(find.byType(ListView), const Offset(0, -600));
    await tester.pumpAndSettle();
    expect(find.byKey(const Key('publish-invitation-content')), findsOneWidget);
  });
}
