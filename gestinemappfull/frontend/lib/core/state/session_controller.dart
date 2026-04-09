import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../models/company_model.dart';
import '../network/api_client.dart';
import 'session_state.dart';

final apiClientProvider = Provider<ApiClient>((ref) => ApiClient());

final sessionControllerProvider =
    StateNotifierProvider<SessionController, SessionState>((ref) {
      return SessionController(ref.read(apiClientProvider));
    });

class SessionController extends StateNotifier<SessionState> {
  SessionController(this._apiClient) : super(SessionState.initial());

  final ApiClient _apiClient;

  Future<void> login({required String email, required String password}) async {
    state = state.copyWith(isBusy: true, clearError: true);
    try {
      final loginResult = await _apiClient.login(
        email: email,
        password: password,
      );
      final user = await _apiClient.getMe(token: loginResult.token);
      final companies = await _apiClient.getCompanies(token: loginResult.token);
      state = state.copyWith(
        stage: SessionStage.selectingCompany,
        token: loginResult.token,
        user: user,
        companies: companies,
        isBusy: false,
        clearError: true,
        clearDashboard: true,
        clearCompany: true,
      );
    } on ApiException catch (exc) {
      state = state.copyWith(isBusy: false, errorMessage: exc.message);
    }
  }

  Future<void> refreshCompanies() async {
    if (state.token == null) {
      return;
    }
    state = state.copyWith(isBusy: true, clearError: true);
    try {
      final companies = await _apiClient.getCompanies(token: state.token!);
      state = state.copyWith(
        stage: SessionStage.selectingCompany,
        companies: companies,
        isBusy: false,
        clearCompany: true,
        clearDashboard: true,
        clearError: true,
      );
    } on ApiException catch (exc) {
      state = state.copyWith(isBusy: false, errorMessage: exc.message);
    }
  }

  Future<void> createCompany({required String name, String? cif}) async {
    if (state.token == null) {
      return;
    }
    state = state.copyWith(isBusy: true, clearError: true);
    try {
      final company = await _apiClient.createCompany(
        token: state.token!,
        name: name,
        cif: cif,
      );
      final companies = [...state.companies, company]
        ..sort((a, b) => a.name.compareTo(b.name));
      state = state.copyWith(
        companies: companies,
        isBusy: false,
        clearError: true,
      );
    } on ApiException catch (exc) {
      state = state.copyWith(isBusy: false, errorMessage: exc.message);
    }
  }

  Future<void> selectCompany(CompanyModel company) async {
    if (state.token == null) {
      return;
    }
    state = state.copyWith(isBusy: true, clearError: true);
    try {
      final dashboard = await _apiClient.getDashboardSummary(
        token: state.token!,
        companyId: company.id,
      );
      state = state.copyWith(
        stage: SessionStage.ready,
        activeCompany: company,
        dashboard: dashboard,
        isBusy: false,
        clearError: true,
      );
    } on ApiException catch (exc) {
      state = state.copyWith(isBusy: false, errorMessage: exc.message);
    }
  }

  void backToCompanySelector() {
    state = state.copyWith(
      stage: SessionStage.selectingCompany,
      clearCompany: true,
      clearDashboard: true,
      clearError: true,
    );
  }

  void logout() {
    state = SessionState.initial();
  }
}
