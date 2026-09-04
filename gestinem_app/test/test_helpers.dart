import 'dart:convert';
import 'dart:typed_data';

import 'package:dio/dio.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:gestinem/features/auth/domain/user_profile.dart';
import 'package:gestinem/features/auth/presentation/auth_controller.dart';

const testProfile = UserProfile(
  id: 'client-1',
  name: 'Cliente Prueba',
  email: 'cliente@example.test',
  type: UserType.client,
);
const testSession = AuthSession(token: 'test-token', profile: testProfile);

class FakeSessionController extends SessionController {
  FakeSessionController(super.ref, [AuthSession? session = testSession]) {
    state = AsyncData(session);
  }

  @override
  Future<void> restore() async {}

  @override
  Future<void> loginClient(String email, String password) async {}

  @override
  Future<void> loginStaff() async {}
}

class JsonAdapter implements HttpClientAdapter {
  JsonAdapter(this.payload, {this.statusCode = 200});
  final Object payload;
  final int statusCode;
  RequestOptions? lastRequest;

  @override
  Future<ResponseBody> fetch(
    RequestOptions options,
    Stream<Uint8List>? requestStream,
    Future<void>? cancelFuture,
  ) async {
    lastRequest = options;
    return ResponseBody.fromString(
      jsonEncode(payload),
      statusCode,
      headers: {
        Headers.contentTypeHeader: ['application/json'],
      },
    );
  }

  @override
  void close({bool force = false}) {}
}
