import 'dart:convert';

import 'package:dio/dio.dart';
import 'package:file_picker/file_picker.dart';

import '../../../core/api/api_client.dart';
import '../domain/company_profile.dart';
import '../domain/profile_change_request.dart';

class CompanyProfileRepository {
  CompanyProfileRepository(this._api);

  final ApiClient _api;

  Future<CompanyProfile> getProfile() async {
    final response = await _api.dio.get('/client/company-profile');
    return CompanyProfile.fromJson(response.data as Map<String, dynamic>);
  }

  Future<Map<String, dynamic>> requestChanges({
    required Map<String, dynamic> changes,
    String notes = '',
    PlatformFile? logo,
  }) async {
    final data = <String, dynamic>{
      'changes_json': jsonEncode(changes),
      'notes': notes.trim(),
    };
    if (logo != null) {
      data['logo'] = MultipartFile.fromBytes(
        await logo.readAsBytes(),
        filename: logo.name,
      );
    }
    final response = await _api.dio.post<Map<String, dynamic>>(
      '/client/profile-change-requests',
      data: FormData.fromMap(data),
    );
    return response.data!;
  }

  Future<List<ProfileChangeRequest>> getChangeRequests() async {
    final response = await _api.dio.get<List<dynamic>>(
      '/client/profile-change-requests',
    );
    return (response.data ?? const [])
        .map(
          (item) => ProfileChangeRequest.fromJson(
            Map<String, dynamic>.from(item as Map),
          ),
        )
        .toList(growable: false);
  }
}
