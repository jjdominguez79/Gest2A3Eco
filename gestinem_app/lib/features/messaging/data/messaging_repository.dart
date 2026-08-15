import 'dart:typed_data';

import 'package:dio/dio.dart';
import 'package:file_picker/file_picker.dart';

import '../../../core/api/api_client.dart';
import '../../auth/domain/user_profile.dart';
import '../domain/conversation.dart';
import '../domain/message.dart';

class MessagingRepository {
  MessagingRepository(this._api);

  final ApiClient _api;

  String _audience(UserProfile profile) => profile.type.name;

  Future<List<Conversation>> conversations(UserProfile profile) async {
    final path = profile.type == UserType.client ? '/client/conversations' : '/staff/conversations';
    final response = await _api.dio.get<List<dynamic>>(path);
    return response.data!
        .map((item) => Conversation.fromJson(item as Map<String, dynamic>))
        .toList(growable: false);
  }

  Future<List<Message>> messages(UserProfile profile, String conversationId) async {
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
      uploads.add(MultipartFile.fromBytes(await file.readAsBytes(), filename: file.name));
    }
    final fields = <String, dynamic>{
      'body': body,
      'idempotency_key': '${DateTime.now().microsecondsSinceEpoch}-${profile.id}',
      'files': uploads,
    };
    if (replyToMessageId != null) fields['reply_to_message_id'] = replyToMessageId;
    final form = FormData.fromMap(fields);
    final response = await _api.dio.post<Map<String, dynamic>>(
      '/${_audience(profile)}/conversations/$conversationId/messages',
      data: form,
    );
    return Message.fromJson(response.data!);
  }

  Future<void> markRead(UserProfile profile, String conversationId) => _api.dio.post<void>(
        '/${_audience(profile)}/conversations/$conversationId/read',
      );

  Future<void> changeState(String conversationId, String state) => _api.dio.patch<void>(
        '/staff/conversations/$conversationId',
        data: {'state': state},
      );

  Future<void> softDelete(UserProfile profile, String messageId) => _api.dio.delete<void>(
        '/${_audience(profile)}/messages/$messageId',
        data: {'reason': ''},
      );

  Future<void> softDeleteInternal(String messageId) => _api.dio.delete<void>(
        '/staff/internal/messages/$messageId',
        data: {'reason': ''},
      );

  Future<Uint8List> download(UserProfile profile, Attachment attachment) {
    final path = profile.type == UserType.client
        ? '/client/attachments/${attachment.id}'
        : '/staff/attachments/${attachment.id}/download';
    return _api.download(path);
  }

  Future<List<InternalThread>> internalThreads() async {
    final response = await _api.dio.get<List<dynamic>>('/staff/internal/threads');
    return response.data!
        .map((item) => InternalThread.fromJson(item as Map<String, dynamic>))
        .toList(growable: false);
  }

  Future<List<Message>> internalMessages(String threadId) async {
    final response = await _api.dio.get<List<dynamic>>('/staff/internal/threads/$threadId/messages');
    return response.data!
        .map((item) => Message.fromJson(item as Map<String, dynamic>))
        .toList(growable: false);
  }

  Future<Message> sendInternal(String threadId, String body, {String? replyToMessageId}) async {
    final fields = <String, dynamic>{
      'body': body,
      'idempotency_key': DateTime.now().microsecondsSinceEpoch.toString(),
    };
    if (replyToMessageId != null) fields['reply_to_message_id'] = replyToMessageId;
    final response = await _api.dio.post<Map<String, dynamic>>(
      '/staff/internal/threads/$threadId/messages',
      data: FormData.fromMap(fields),
    );
    return Message.fromJson(response.data!);
  }
}
