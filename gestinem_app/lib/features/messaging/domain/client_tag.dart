class ClientTag {
  const ClientTag({required this.id, required this.name, required this.color});

  factory ClientTag.fromJson(Map<String, dynamic> json) => ClientTag(
    id: json['id'] as String? ?? '',
    name: json['name'] as String? ?? '',
    color: json['color'] as String? ?? '#6750A4',
  );

  final String id;
  final String name;
  final String color;
}
