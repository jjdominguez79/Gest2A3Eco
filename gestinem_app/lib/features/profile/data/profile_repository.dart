import 'package:dio/dio.dart';
import 'package:file_picker/file_picker.dart';

import '../../../core/api/api_client.dart';
import '../../../core/images/avatar_image.dart';

class ProfileRepository {
  ProfileRepository(this.api);
  final ApiClient api;

  Future<void> updateChatAlias(String alias) async {
    await api.dio.patch<void>('/staff/me', data: {'chat_alias': alias});
  }

  Future<String> uploadAvatar(PlatformFile file) async {
    final bytes = await prepararAvatar(file);
    final form = FormData.fromMap({
      'avatar': MultipartFile.fromBytes(bytes, filename: 'avatar.jpg'),
    });
    final response = await api.dio.put<Map<String, dynamic>>(
      '/staff/me/avatar',
      data: form,
    );
    return response.data?['avatar_url'] as String? ?? '';
  }
}
