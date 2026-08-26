import 'dart:typed_data';

import 'package:dio/dio.dart';
import 'package:file_picker/file_picker.dart';

import '../../../core/api/api_client.dart';
import '../../auth/domain/user_profile.dart';
import '../domain/client_organization.dart';
import '../domain/conversation.dart';
import '../domain/message.dart';

class MessagingRepository {
  MessagingRepository(this._api);

  final ApiClient _api;

  String _audience(UserProfile profile) => profile.type.name;

  Future<List<Conversation>> conversations(UserProfile profile) async {
    final path = profile.type == UserType.client
        ? '/client/conversations'
        : '/staff/conversations';
    final response = await _api.dio.get<List<dynamic>>(path);
    return response.data!
        .map((item) => Conversation.fromJson(item as Map<String, dynamic>))
        .toList(growable: false);
  }

  Future<List<Conversation>> conversationTargets() async {
    final response = await _api.dio.get<List<dynamic>>(
      '/staff/conversation-targets',
    );
    return response.data!
        .map((item) => Conversation.fromJson(item as Map<String, dynamic>))
        .toList(growable: false);
  }

  Future<Conversation> startConversation(String conversationId) async {
    final response = await _api.dio.post<Map<String, dynamic>>(
      '/staff/conversations/$conversationId/start',
    );
    return Conversation.fromJson(response.data!);
  }

  Future<Conversation> startDirectConversation(String companyCode) async {
    final targets = await conversationTargets();
    final direct = targets.where(
      (item) => item.companyCode == companyCode && item.kind == 'private',
    );
    if (direct.isEmpty) {
      throw StateError('No tienes disponible el chat directo de este cliente');
    }
    return startConversation(direct.first.id);
  }

  Future<List<ClientOrganization>> clientOrganizations() async {
    final response = await _api.dio.get<List<dynamic>>(
      '/staff/admin/organizations',
    );
    return response.data!
        .map(
          (item) => ClientOrganization.fromJson(item as Map<String, dynamic>),
        )
        .toList(growable: false);
  }

  Future<List<Message>> messages(
    UserProfile profile,
    String conversationId,
  ) async {
    final response = await _api.dio.get<List<dynamic>>(
      '/${_audience(profile)}/conversations/$conversationId/messages',
    );
    return response.data!
        .map((item) => Message.fromJson(item as Map<String, dynamic>))
        .toList(growable: false);
  }

  Future<Message> send(
    UserProfile profile,
    String conversationId,
    String body,
    List<PlatformFile> files, {
    String? replyToMessageId,
  }) async {
    final uploads = <MultipartFile>[];
    for (final file in files) {
      uploads.add(
        MultipartFile.fromBytes(await file.readAsBytes(), filename: file.name),
      );
    }
    final fields = <String, dynamic>{
      'body': body,
      'idempotency_key':
          '${DateTime.now().microsecondsSinceEpoch}-${profile.id}',
      'files': uploads,
    };
    if (replyToMessageId != null) {
      fields['reply_to_message_id'] = replyToMessageId;
    }
    final form = FormData.fromMap(fields);
    final response = await _api.dio.post<Map<String, dynamic>>(
      '/${_audience(profile)}/conversations/$conversationId/messages',
      data: form,
    );
    return Message.fromJson(response.data!);
  }

  Future<void> markRead(UserProfile profile, String conversationId) => _api.dio
      .post<void>('/${_audience(profile)}/conversations/$conversationId/read');

  Future<void> markUnread(UserProfile profile, String conversationId) =>
      _api.dio.delete<void>(
        '/${_audience(profile)}/conversations/$conversationId/read',
      );

  Future<void> changeState(String conversationId, String state) =>
      _api.dio.patch<void>(
        '/staff/conversations/$conversationId',
        data: {'state': state},
      );

  Future<void> setClientAccess(String companyCode, bool active) =>
      _api.dio.patch<void>(
        '/staff/admin/organizations/$companyCode/client-access',
        data: {'active': active},
      );

  Future<Map<String, dynamic>> inviteClient({
    required String companyCode,
    required String name,
    required String email,
    bool sendEmail = true,
  }) async {
    final response = await _api.dio.post<Map<String, dynamic>>(
      '/staff/admin/invitations',
      data: {
        'company_code': companyCode,
        'name': name,
        'email': email,
        'send_email': sendEmail,
      },
    );
    return response.data!;
  }

  Future<List<Organization>> organizations() async {
    final response = await _api.dio.get<List<dynamic>>(
      '/staff/admin/organizations',
    );
    return response.data!
        .map((item) => Organization.fromJson(item as Map<String, dynamic>))
        .toList(growable: false);
  }

  Future<Map<String, dynamic>> latestAppVersion(String platform) async {
    final response = await _api.dio.get<Map<String, dynamic>>(
      '/public/app-version',
      queryParameters: {'platform': platform},
    );
    return response.data!;
  }

  Future<void> softDelete(UserProfile profile, String messageId) =>
      _api.dio.delete<void>(
        '/${_audience(profile)}/messages/$messageId',
        data: {'reason': ''},
      );

  Future<void> softDeleteInternal(String messageId) => _api.dio.delete<void>(
    '/staff/internal/messages/$messageId',
    data: {'reason': ''},
  );

  /// Descarga el contenido de un adjunto saliente (solo cliente).
  /// Devuelve los bytes y el download-id para confirmar la descarga.
  Future<(Uint8List bytes, String downloadId)> downloadWithId(
    Attachment attachment,
  ) async {
    final response = await _api.dio.get<List<int>>(
      '/client/attachments/${attachment.id}',
      options: Options(responseType: ResponseType.bytes),
    );
    final bytes = Uint8List.fromList(response.data ?? const []);
    final downloadId = response.headers.value('x-download-id') ?? '';
    return (bytes, downloadId);
  }

  /// Confirma que Flutter guardo correctamente el archivo descargado.
  Future<void> confirmDownload(String attachmentId, String downloadId) async {
    await _api.dio.post<void>(
      '/client/attachments/$attachmentId/confirm-download',
      data: FormData.fromMap({'download_id': downloadId}),
    );
  }

  Future<List<AttachmentDownload>> attachmentDownloads(
    String attachmentId,
  ) async {
    final response = await _api.dio.get<List<dynamic>>(
      '/staff/attachments/$attachmentId/downloads',
    );
    return response.data!
        .map(
          (item) => AttachmentDownload.fromJson(item as Map<String, dynamic>),
        )
        .toList(growable: false);
  }

  Future<void> withdrawAttachment(String attachmentId, String reason) =>
      _api.dio.post<void>(
        '/staff/admin/attachments/$attachmentId/withdraw',
        data: {'reason': reason},
      );

  Future<Uint8List> download(UserProfile profile, Attachment attachment) {
    final path = profile.type == UserType.client
        ? '/client/attachments/${attachment.id}'
        : '/staff/attachments/${attachment.id}/download';
    return _api.download(path);
  }

  Future<List<InternalThread>> internalThreads() async {
    final response = await _api.dio.get<List<dynamic>>(
      '/staff/internal/threads',
    );
    return response.data!
        .map((item) => InternalThread.fromJson(item as Map<String, dynamic>))
        .toList(growable: false);
  }

  Future<InternalThread> startEmployeeChat(String employeeId) async {
    final response = await _api.dio.post<Map<String, dynamic>>(
      '/staff/internal/direct/$employeeId',
    );
    return InternalThread.fromJson(response.data!);
  }

  Future<List<Message>> internalMessages(String threadId) async {
    final response = await _api.dio.get<List<dynamic>>(
      '/staff/internal/threads/$threadId/messages',
    );
    return response.data!
        .map((item) => Message.fromJson(item as Map<String, dynamic>))
        .toList(growable: false);
  }

  Future<void> markInternalRead(String threadId) =>
      _api.dio.post<void>('/staff/internal/threads/$threadId/read');

  Future<Message> sendInternal(
    String threadId,
    String body,
    List<PlatformFile> files, {
    String? replyToMessageId,
  }) async {
    final uploads = <MultipartFile>[];
    for (final file in files) {
      uploads.add(
        MultipartFile.fromBytes(await file.readAsBytes(), filename: file.name),
      );
    }
    final fields = <String, dynamic>{
      'body': body,
      'idempotency_key': DateTime.now().microsecondsSinceEpoch.toString(),
      'files': uploads,
    };
    if (replyToMessageId != null) {
      fields['reply_to_message_id'] = replyToMessageId;
    }
    final response = await _api.dio.post<Map<String, dynamic>>(
      '/staff/internal/threads/$threadId/messages',
      data: FormData.fromMap(fields),
    );
    return Message.fromJson(response.data!);
  }

  Future<Uint8List> downloadInternalAttachment(String attachmentId) =>
      _api.download('/staff/internal/attachments/$attachmentId');

  /// Vista unificada del cliente: metadatos de todas las conversaciones.
  Future<Map<String, dynamic>> unifiedConversation() async {
    final response = await _api.dio.get<Map<String, dynamic>>(
      '/client/unified-conversation',
    );
    return response.data!;
  }

  /// Todos los mensajes del cliente (cross-canal) en orden cronologico.
  Future<List<Message>> unifiedMessages({int limit = 100}) async {
    final response = await _api.dio.get<List<dynamic>>(
      '/client/unified-messages',
      queryParameters: {'limit': limit},
    );
    return response.data!
        .map((item) => Message.fromJson(item as Map<String, dynamic>))
        .toList(growable: false);
  }

  /// Enviar mensaje en la vista unificada del cliente.
  Future<Message> sendUnified(
    String body,
    List<PlatformFile> files, {
    String? replyToMessageId,
  }) async {
    final uploads = <MultipartFile>[];
    for (final file in files) {
      uploads.add(
        MultipartFile.fromBytes(await file.readAsBytes(), filename: file.name),
      );
    }
    final fields = <String, dynamic>{
      'body': body,
      'idempotency_key': '${DateTime.now().microsecondsSinceEpoch}',
      'files': uploads,
    };
    if (replyToMessageId != null) {
      fields['reply_to_message_id'] = replyToMessageId;
    }
    final form = FormData.fromMap(fields);
    final response = await _api.dio.post<Map<String, dynamic>>(
      '/client/unified-messages',
      data: form,
    );
    return Message.fromJson(response.data!);
  }

  /// Marca como leidas todas las conversaciones del cliente.
  Future<void> markAllRead() async {
    final meta = await unifiedConversation();
    final channelIds = meta['channel_ids'] as Map<String, dynamic>? ?? {};
    for (final id in channelIds.values) {
      try {
        await _api.dio.post<void>('/client/conversations/$id/read');
      } catch (_) {}
    }
  }
}
