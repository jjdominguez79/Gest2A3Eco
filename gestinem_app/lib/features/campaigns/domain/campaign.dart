class Campaign {
  const Campaign({required this.id, required this.name, required this.status, required this.recipientCount});
  factory Campaign.fromJson(Map<String, dynamic> json) => Campaign(
        id: json['id'] as String,
        name: json['name'] as String,
        status: json['status'] as String,
        recipientCount: json['recipient_count'] as int? ?? 0,
      );
  final String id;
  final String name;
  final String status;
  final int recipientCount;
}
