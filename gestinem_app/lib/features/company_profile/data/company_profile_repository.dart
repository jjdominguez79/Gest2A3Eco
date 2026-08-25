import '../../../core/api/api_client.dart';
import '../domain/company_profile.dart';

class CompanyProfileRepository {
  CompanyProfileRepository(this._api);

  final ApiClient _api;

  Future<CompanyProfile> getProfile() async {
    final response = await _api.dio.get('/client/company-profile');
    return CompanyProfile.fromJson(
      response.data as Map<String, dynamic>,
    );
  }
}
