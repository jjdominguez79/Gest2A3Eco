import '../../../core/api/api_client.dart';
import '../domain/campaign.dart';

class CampaignsRepository {
  CampaignsRepository(this._api);
  final ApiClient _api;

  Future<List<Campaign>> list() async {
    final response = await _api.dio.get<List<dynamic>>(
      '/staff/admin/campaigns',
    );
    return response.data!
        .map((item) => Campaign.fromJson(item as Map<String, dynamic>))
        .toList();
  }

  Future<List<CampaignClientTarget>> clients() async {
    final response = await _api.dio.get<List<dynamic>>(
      '/staff/admin/campaign-targets/clients',
    );
    return response.data!
        .map(
          (item) => CampaignClientTarget.fromJson(item as Map<String, dynamic>),
        )
        .toList();
  }

  Future<void> create({
    required String name,
    required String body,
    required String channel,
    required bool allClients,
    required List<String> groupIds,
    required List<String> clientIds,
  }) => _api.dio.post<void>(
    '/staff/admin/campaigns',
    data: {
      'name': name,
      'body': body,
      'channel': channel,
      'all_clients': allClients,
      'group_ids': groupIds,
      'client_ids': clientIds,
    },
  );

  Future<void> retry(String id) =>
      _api.dio.post<void>('/staff/admin/campaigns/$id/retry');
}
