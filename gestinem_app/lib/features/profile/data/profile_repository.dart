import 'package:dio/dio.dart';
import 'package:file_picker/file_picker.dart';

import '../../../core/api/api_client.dart';

class ProfileRepository {
  ProfileRepository(this.api);
  final ApiClient api;

  Future<void> updateChatAlias(String alias) async {
    await api.dio.patch<void>(
      '/api/v1/messaging/staff/me',
      data: {'chat_alias': alias},
    );
  }

  Future<String> uploadAvatar(PlatformFile file) async {
    final bytes = await file.readAsBytes();
    final form = FormData.fromMap({
      'avatar': MultipartFile.fromBytes(bytes, filename: file.name),
    });
    final response = await api.dio.put<Map<String, dynamic>>(
      '/api/v1/messaging/staff/me/avatar',
      data: form,
    );
    return response.data?['avatar_url'] as String? ?? '';
  }
}
