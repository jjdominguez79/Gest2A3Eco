import '../../../core/api/api_client.dart';
import '../domain/group.dart';

class GroupsRepository {
  GroupsRepository(this._api);
  final ApiClient _api;

  Future<List<MessagingGroup>> list() async {
    final response = await _api.dio.get<List<dynamic>>('/staff/groups');
    return response.data!
        .map((item) => MessagingGroup.fromJson(item as Map<String, dynamic>))
        .toList();
  }

  Future<MessagingGroup> create(String name, String type) async {
    final response = await _api.dio.post<Map<String, dynamic>>(
      '/staff/admin/groups',
      data: {
        'name': name,
        'description': '',
        'group_type': type,
        'active': true,
      },
    );
    return MessagingGroup.fromJson(response.data!);
  }

  Future<MessagingGroup> update(MessagingGroup group, String name) async {
    final response = await _api.dio.patch<Map<String, dynamic>>(
      '/staff/admin/groups/${group.id}',
      data: {
        'name': name,
        'description': '',
        'group_type': group.type,
        'active': true,
      },
    );
    return MessagingGroup.fromJson(response.data!);
  }

  Future<void> addMember(String groupId, String memberType, String memberId) =>
      _api.dio.post<void>(
        '/staff/admin/groups/$groupId/members',
        data: {
          'member_type': memberType,
          'member_id': memberId,
          'role': 'member',
        },
      );

  Future<void> removeMember(String groupId, String memberId) =>
      _api.dio.delete<void>('/staff/admin/groups/$groupId/members/$memberId');

  Future<void> delete(String groupId) =>
      _api.dio.delete<void>('/staff/admin/groups/$groupId');
}
