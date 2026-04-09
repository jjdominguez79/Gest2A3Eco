import '../models/company_model.dart';
import '../models/dashboard_summary_model.dart';
import '../models/user_model.dart';

enum SessionStage { unauthenticated, selectingCompany, ready }

class SessionState {
  const SessionState({
    required this.stage,
    this.token,
    this.user,
    this.companies = const [],
    this.activeCompany,
    this.dashboard,
    this.isBusy = false,
    this.errorMessage,
  });

  final SessionStage stage;
  final String? token;
  final UserModel? user;
  final List<CompanyModel> companies;
  final CompanyModel? activeCompany;
  final DashboardSummaryModel? dashboard;
  final bool isBusy;
  final String? errorMessage;

  factory SessionState.initial() {
    return const SessionState(stage: SessionStage.unauthenticated);
  }

  SessionState copyWith({
    SessionStage? stage,
    String? token,
    UserModel? user,
    List<CompanyModel>? companies,
    CompanyModel? activeCompany,
    DashboardSummaryModel? dashboard,
    bool? isBusy,
    String? errorMessage,
    bool clearError = false,
    bool clearCompany = false,
    bool clearDashboard = false,
  }) {
    return SessionState(
      stage: stage ?? this.stage,
      token: token ?? this.token,
      user: user ?? this.user,
      companies: companies ?? this.companies,
      activeCompany: clearCompany ? null : activeCompany ?? this.activeCompany,
      dashboard: clearDashboard ? null : dashboard ?? this.dashboard,
      isBusy: isBusy ?? this.isBusy,
      errorMessage: clearError ? null : errorMessage ?? this.errorMessage,
    );
  }
}
