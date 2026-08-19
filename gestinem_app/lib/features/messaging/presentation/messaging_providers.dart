import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../auth/presentation/auth_controller.dart';
import '../../../core/websocket/realtime_service.dart';
import '../../profile/data/profile_repository.dart';
import '../data/messaging_repository.dart';
import '../domain/conversation.dart';
import '../domain/message.dart';

final messagingRepositoryProvider = Provider<MessagingRepository>((ref) {
  return MessagingRepository(ref.watch(apiClientProvider));
});

final realtimeServiceProvider = Provider<RealtimeService>(
  (ref) => RealtimeService(),
);

final profileRepositoryProvider = Provider<ProfileRepository>((ref) {
  return ProfileRepository(ref.watch(apiClientProvider));
});

final conversationsProvider = FutureProvider.autoDispose<List<Conversation>>((
  ref,
) async {
  final profile = ref.watch(sessionProvider).valueOrNull!.profile;
  return ref.watch(messagingRepositoryProvider).conversations(profile);
});

final messagesProvider = FutureProvider.autoDispose
    .family<List<Message>, String>((ref, id) async {
      final profile = ref.watch(sessionProvider).valueOrNull!.profile;
      return ref.watch(messagingRepositoryProvider).messages(profile, id);
    });

final internalThreadsProvider =
    FutureProvider.autoDispose<List<InternalThread>>((ref) {
      return ref.watch(messagingRepositoryProvider).internalThreads();
    });

final internalMessagesProvider = FutureProvider.autoDispose
    .family<List<Message>, String>((ref, id) {
      return ref.watch(messagingRepositoryProvider).internalMessages(id);
    });

/// Metadatos de conversacion unificada del cliente.
final unifiedConversationProvider =
    FutureProvider.autoDispose<Map<String, dynamic>>((ref) async {
      return ref.watch(messagingRepositoryProvider).unifiedConversation();
    });

/// Mensajes unificados del cliente (todos los canales, cronologico).
final unifiedMessagesProvider = FutureProvider.autoDispose<List<Message>>((
  ref,
) async {
  return ref.watch(messagingRepositoryProvider).unifiedMessages();
});
