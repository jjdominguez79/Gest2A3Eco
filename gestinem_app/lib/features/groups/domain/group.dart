class MessagingGroup {
  const MessagingGroup({
    required this.id,
    required this.name,
    required this.type,
    required this.members,
  });

  factory MessagingGroup.fromJson(Map<String, dynamic> json) => MessagingGroup(
    id: json['id'] as String,
    name: json['name'] as String,
    type: json['group_type'] as String,
    members: (json['members'] as List<dynamic>? ?? const [])
        .map((item) => GroupMember.fromJson(item as Map<String, dynamic>))
        .toList(growable: false),
  );

  final String id;
  final String name;
  final String type;
  final List<GroupMember> members;
}

class GroupMember {
  const GroupMember({
    required this.id,
    required this.memberType,
    required this.memberId,
    required this.role,
  });
  factory GroupMember.fromJson(Map<String, dynamic> json) => GroupMember(
    id: json['id'] as String,
    memberType: json['member_type'] as String,
    memberId: json['member_id'] as String,
    role: json['role'] as String,
  );
  final String id;
  final String memberType;
  final String memberId;
  final String role;
}
