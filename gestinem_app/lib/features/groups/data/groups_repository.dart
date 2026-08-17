import '../../../core/api/api_client.dart';
import '../domain/group.dart';

class GroupsRepository {
  GroupsRepository(this._api);
  final ApiClient _api;

  Future<List<MessagingGroup>> list() async {
    final response = await _api.dio.get<List<dynamic>>('/staff/groups');
    return response.data!.map((item) => MessagingGroup.fromJson(item as Map<String, dynamic>)).toList();
  }

  Future<void> create(String name, String type) => _api.dio.post<void>(
        '/staff/admin/groups',
        data: {'name': name, 'description': '', 'group_type': type, 'active': true},
      );

  Future<void> addMember(String groupId, String memberType, String memberId) => _api.dio.post<void>(
        '/staff/admin/groups/$groupId/members',
        data: {'member_type': memberType, 'member_id': memberId, 'role': 'member'},
      );
}
