import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../auth/domain/user_profile.dart';
import '../../auth/presentation/auth_controller.dart';
import '../../../core/websocket/realtime_service.dart';
import '../../../core/storage/composer_preferences_storage.dart';
import '../../profile/data/profile_repository.dart';
import '../data/messaging_repository.dart';
import '../domain/client_organization.dart';
import '../domain/conversation.dart';
import '../domain/internal_task.dart';
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

final composerPreferencesStorageProvider = Provider<ComposerPreferencesStorage>(
  (_) => ComposerPreferencesStorage(),
);

final sendWithEnterProvider = FutureProvider<bool>((ref) {
  final profile = ref.watch(sessionProvider).valueOrNull!.profile;
  final userKey = '${profile.type.name}.${profile.id}';
  return ref
      .watch(composerPreferencesStorageProvider)
      .readSendWithEnter(userKey);
});

Future<void> setSendWithEnter(WidgetRef ref, bool enabled) async {
  final profile = ref.read(sessionProvider).valueOrNull!.profile;
  final userKey = '${profile.type.name}.${profile.id}';
  await ref
      .read(composerPreferencesStorageProvider)
      .writeSendWithEnter(userKey, enabled);
  ref.invalidate(sendWithEnterProvider);
}

final conversationsProvider = FutureProvider.autoDispose<List<Conversation>>((
  ref,
) async {
  final profile = ref.watch(sessionProvider).valueOrNull!.profile;
  return ref.watch(messagingRepositoryProvider).conversations(profile);
});

final conversationTargetsProvider =
    FutureProvider.autoDispose<List<Conversation>>((ref) {
      return ref.watch(messagingRepositoryProvider).conversationTargets();
    });

final clientOrganizationsProvider =
    FutureProvider.autoDispose<List<ClientOrganization>>((ref) {
      return ref.watch(messagingRepositoryProvider).clientOrganizations();
    });

final messagesProvider = FutureProvider.autoDispose
    .family<List<Message>, String>((ref, id) async {
      final profile = ref.watch(sessionProvider).valueOrNull!.profile;
      return ref.watch(messagingRepositoryProvider).messages(profile, id);
    });

final internalThreadsProvider = FutureProvider<List<InternalThread>>((ref) {
  final session = ref.watch(sessionProvider).valueOrNull;
  if (session == null) return const <InternalThread>[];
  return ref.watch(messagingRepositoryProvider).internalThreads();
});

final staffInboxProvider = FutureProvider<StaffInboxData>((ref) {
  final session = ref.watch(sessionProvider).valueOrNull;
  if (session == null || session.profile.type != UserType.staff) {
    return const StaffInboxData(conversations: [], threads: [], labels: []);
  }
  return ref.watch(messagingRepositoryProvider).staffInbox();
});

final chatLabelsProvider = FutureProvider<List<ChatLabel>>((ref) {
  final session = ref.watch(sessionProvider).valueOrNull;
  if (session == null || session.profile.type != UserType.staff) {
    return const <ChatLabel>[];
  }
  return ref.watch(messagingRepositoryProvider).chatLabels();
});

/// Numero total que debe mostrarse en el icono de la barra de tareas.
///
/// Para empleados suma los canales de clientes y los chats internos. Para
/// clientes solo existen sus conversaciones con Gestinem.
final pendingMessagesCountProvider = FutureProvider.autoDispose<int>((
  ref,
) async {
  final session = ref.watch(sessionProvider).valueOrNull;
  if (session == null) return 0;

  if (session.profile.type == UserType.staff) {
    final inbox = await ref.watch(staffInboxProvider.future);
    return inbox.conversations.fold<int>(
          0,
          (sum, conversation) => sum + conversation.unreadCount,
        ) +
        inbox.threads.fold<int>(0, (sum, thread) => sum + thread.unreadCount);
  }
  final conversations = await ref.watch(conversationsProvider.future);
  return conversations.fold<int>(
    0,
    (sum, conversation) => sum + conversation.unreadCount,
  );
});

final internalMessagesProvider = FutureProvider.family<List<Message>, String>((
  ref,
  id,
) {
  final session = ref.watch(sessionProvider).valueOrNull;
  if (session == null) return const <Message>[];
  return ref.watch(messagingRepositoryProvider).internalMessages(id);
});

final internalTasksProvider = FutureProvider.autoDispose
    .family<List<InternalTask>, String>((ref, id) {
      return ref.watch(messagingRepositoryProvider).internalTasks(id);
    });

/// Todas las organizaciones con su estado de acceso (solo admin).
final organizationsProvider = FutureProvider.autoDispose<List<Organization>>((
  ref,
) {
  return ref.watch(messagingRepositoryProvider).organizations();
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
