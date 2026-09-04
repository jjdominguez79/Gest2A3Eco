class ProfileChangeRequest {
  const ProfileChangeRequest({
    required this.id,
    required this.status,
    required this.changes,
    required this.createdAt,
    this.reviewNote = '',
  });

  final String id;
  final String status;
  final Map<String, dynamic> changes;
  final DateTime? createdAt;
  final String reviewNote;

  bool get isPending => status == 'pending';

  factory ProfileChangeRequest.fromJson(Map<String, dynamic> json) {
    return ProfileChangeRequest(
      id: json['id'] as String? ?? '',
      status: json['status'] as String? ?? 'pending',
      changes: Map<String, dynamic>.from(
        json['changes'] as Map<String, dynamic>? ?? const {},
      ),
      createdAt: DateTime.tryParse(json['created_at'] as String? ?? ''),
      reviewNote: json['review_note'] as String? ?? '',
    );
  }
}
