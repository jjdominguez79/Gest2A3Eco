class InternalTaskAssignment {
  const InternalTaskAssignment({
    required this.staffId,
    required this.name,
    required this.completed,
    this.completedAt,
    this.completedByName = '',
  });

  factory InternalTaskAssignment.fromJson(Map<String, dynamic> json) =>
      InternalTaskAssignment(
        staffId: json['staff_id'] as String? ?? '',
        name: json['name'] as String? ?? '',
        completed: json['completed'] as bool? ?? false,
        completedAt: json['completed_at'] == null
            ? null
            : DateTime.parse(json['completed_at'] as String).toLocal(),
        completedByName: json['completed_by_name'] as String? ?? '',
      );

  final String staffId;
  final String name;
  final bool completed;
  final DateTime? completedAt;
  final String completedByName;
}

class InternalTask {
  const InternalTask({
    required this.id,
    required this.threadId,
    required this.title,
    required this.details,
    required this.createdByStaffId,
    required this.createdByName,
    required this.createdAt,
    required this.updatedAt,
    required this.completed,
    required this.completedCount,
    required this.assigneeCount,
    required this.canComplete,
    required this.myCompleted,
    required this.assignments,
  });

  factory InternalTask.fromJson(Map<String, dynamic> json) => InternalTask(
    id: json['id'] as String,
    threadId: json['thread_id'] as String,
    title: json['title'] as String? ?? '',
    details: json['details'] as String? ?? '',
    createdByStaffId: json['created_by_staff_external_id'] as String? ?? '',
    createdByName: json['created_by_name'] as String? ?? '',
    createdAt: DateTime.parse(json['created_at'] as String).toLocal(),
    updatedAt: DateTime.parse(json['updated_at'] as String).toLocal(),
    completed: json['completed'] as bool? ?? false,
    completedCount: json['completed_count'] as int? ?? 0,
    assigneeCount: json['assignee_count'] as int? ?? 0,
    canComplete: json['can_complete'] as bool? ?? false,
    myCompleted: json['my_completed'] as bool? ?? false,
    assignments: (json['assignments'] as List<dynamic>? ?? const [])
        .map(
          (item) =>
              InternalTaskAssignment.fromJson(item as Map<String, dynamic>),
        )
        .toList(growable: false),
  );

  final String id;
  final String threadId;
  final String title;
  final String details;
  final String createdByStaffId;
  final String createdByName;
  final DateTime createdAt;
  final DateTime updatedAt;
  final bool completed;
  final int completedCount;
  final int assigneeCount;
  final bool canComplete;
  final bool myCompleted;
  final List<InternalTaskAssignment> assignments;
}
