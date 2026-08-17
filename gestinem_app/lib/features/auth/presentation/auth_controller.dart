import 'package:dio/dio.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../core/api/api_client.dart';
import '../../../core/storage/session_storage.dart';
import '../data/auth_repository.dart';
import '../domain/user_profile.dart';

final sessionStorageProvider = Provider<SessionStorage>((ref) => SessionStorage());

final sessionProvider = StateNotifierProvider<SessionController, AsyncValue<AuthSession?>>((ref) {
  final controller = SessionController(ref);
  controller.restore();
  return controller;
});

final apiClientProvider = Provider<ApiClient>((ref) {
  return ApiClient(
    tokenProvider: () => ref.read(sessionProvider).valueOrNull?.token,
    onUnauthorized: () => ref.read(sessionProvider.notifier).expire(),
  );
});

final authRepositoryProvider = Provider<AuthRepository>((ref) {
  return AuthRepository(ref.watch(apiClientProvider).dio);
});

class SessionController extends StateNotifier<AsyncValue<AuthSession?>> {
  SessionController(this.ref) : super(const AsyncLoading());

  final Ref ref;

  Future<void> restore() async {
    final saved = await ref.read(sessionStorageProvider).read();
    if (saved == null) {
      try {
        final exchanged = await ref.read(authRepositoryProvider).exchangeInitialCode();
        if (exchanged != null) {
          await ref.read(sessionStorageProvider).write(exchanged);
          state = AsyncData(exchanged);
          return;
        }
      } catch (_) {
        await ref.read(sessionStorageProvider).clear();
      }
      state = const AsyncData(null);
      return;
    }
    try {
      state = AsyncData(AuthSession(
        token: saved.token,
        profile: await ref.read(authRepositoryProvider).currentProfile(saved),
      ));
    } catch (_) {
      await ref.read(sessionStorageProvider).clear();
      state = const AsyncData(null);
    }
  }

  Future<void> loginClient(String email, String password) async {
    state = const AsyncLoading();
    state = await AsyncValue.guard(() async {
      final session = await ref.read(authRepositoryProvider).loginClient(email, password);
      await ref.read(sessionStorageProvider).write(session);
      return session;
    });
  }

  Future<void> loginStaff() async {
    state = const AsyncLoading();
    state = await AsyncValue.guard(() async {
      final session = await ref.read(authRepositoryProvider).loginStaff();
      await ref.read(sessionStorageProvider).write(session);
      return session;
    });
  }

  Future<void> logout() async {
    final session = state.valueOrNull;
    try {
      if (session != null) await ref.read(authRepositoryProvider).logout(session.profile.type);
    } on DioException {
      // El cierre local debe funcionar aunque la red no este disponible.
    }
    await expire();
  }

  Future<void> expire() async {
    await ref.read(sessionStorageProvider).clear();
    state = const AsyncData(null);
  }
}
