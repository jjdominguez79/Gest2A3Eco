import '../../../core/api/api_client.dart';
import '../domain/campaign.dart';

class CampaignsRepository {
  CampaignsRepository(this._api);
  final ApiClient _api;

  Future<List<Campaign>> list() async {
    final response = await _api.dio.get<List<dynamic>>('/staff/admin/campaigns');
    return response.data!.map((item) => Campaign.fromJson(item as Map<String, dynamic>)).toList();
  }

  Future<void> create({required String name, required String body, required String channel, required bool allClients}) => _api.dio.post<void>(
        '/staff/admin/campaigns',
        data: {'name': name, 'body': body, 'channel': channel, 'all_clients': allClients, 'group_ids': <String>[], 'client_ids': <String>[]},
      );

  Future<void> retry(String id) => _api.dio.post<void>('/staff/admin/campaigns/$id/retry');
}
