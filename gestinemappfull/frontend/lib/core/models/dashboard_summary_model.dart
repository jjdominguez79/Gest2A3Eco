class DashboardSummaryModel {
  const DashboardSummaryModel({
    required this.companyId,
    required this.companyName,
    required this.userFullName,
    required this.userRole,
    required this.pendingTasks,
    required this.recentDocuments,
    required this.alerts,
  });

  final String companyId;
  final String companyName;
  final String userFullName;
  final String userRole;
  final int pendingTasks;
  final int recentDocuments;
  final int alerts;

  factory DashboardSummaryModel.fromJson(Map<String, dynamic> json) {
    return DashboardSummaryModel(
      companyId: json['company_id'] as String,
      companyName: json['company_name'] as String,
      userFullName: json['user_full_name'] as String,
      userRole: json['user_role'] as String,
      pendingTasks: json['pending_tasks'] as int,
      recentDocuments: json['recent_documents'] as int,
      alerts: json['alerts'] as int,
    );
  }
}
