import 'package:dio/dio.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../core/api/api_client.dart';
import '../../../core/storage/session_storage.dart';
import '../../../core/notifications/notifications_service.dart';
import '../../../core/deep_links/deep_link_controller.dart';
import '../data/auth_repository.dart';
import '../domain/user_profile.dart';

final sessionStorageProvider = Provider<SessionStorage>(
  (ref) => SessionStorage(),
);

final sessionProvider =
    StateNotifierProvider<SessionController, AsyncValue<AuthSession?>>((ref) {
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

  Future<AuthSession> _refreshSession(AuthSession saved) async {
    final refreshed = AuthSession(
      token: saved.token,
      profile: await ref.read(authRepositoryProvider).currentProfile(saved),
    );
    await ref.read(sessionStorageProvider).write(refreshed);
    state = AsyncData(refreshed);
    return refreshed;
  }

  Future<void> restore() async {
    final saved = await ref.read(sessionStorageProvider).read();
    if (saved == null) {
      try {
        final exchanged = await ref
            .read(authRepositoryProvider)
            .exchangeInitialCode();
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
      await _refreshSession(saved);
    } catch (_) {
      await ref.read(sessionStorageProvider).clear();
      state = const AsyncData(null);
    }
  }

  Future<void> refreshProfile() async {
    final session = state.valueOrNull;
    if (session == null) return;
    await _refreshSession(session);
  }

  Future<void> loginClient(String email, String password) async {
    state = const AsyncLoading();
    state = await AsyncValue.guard(() async {
      final session = await ref
          .read(authRepositoryProvider)
          .loginClient(email, password);
      await ref.read(sessionStorageProvider).write(session);
      return session;
    });
  }

  Future<void> acceptInvite(String token, String password) async {
    state = const AsyncLoading();
    state = await AsyncValue.guard(() async {
      final session = await ref
          .read(authRepositoryProvider)
          .acceptInvite(token, password);
      await ref.read(sessionStorageProvider).write(session);
      ref.read(deepLinkProvider.notifier).clear();
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
    if (session != null) {
      try {
        await ref
            .read(notificationsServiceProvider)
            .unregister(session, ref.read(apiClientProvider));
      } on DioException {
        // El dispositivo se reasignara al siguiente login si la red no responde.
      }
    }
    try {
      if (session != null) {
        await ref.read(authRepositoryProvider).logout(session.profile.type);
      }
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
