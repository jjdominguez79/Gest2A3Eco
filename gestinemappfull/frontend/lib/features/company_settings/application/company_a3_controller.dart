import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../core/models/company_a3_settings_model.dart';
import '../../../core/network/api_client.dart';
import '../../../core/state/session_controller.dart';

class CompanyA3Scope {
  const CompanyA3Scope({required this.token, required this.companyId});

  final String token;
  final String companyId;
}

class CompanyA3SettingsState {
  const CompanyA3SettingsState({
    required this.isLoading,
    required this.isSaving,
    required this.settings,
    required this.errorMessage,
  });

  factory CompanyA3SettingsState.initial() {
    return const CompanyA3SettingsState(
      isLoading: true,
      isSaving: false,
      settings: null,
      errorMessage: null,
    );
  }

  final bool isLoading;
  final bool isSaving;
  final CompanyA3SettingsModel? settings;
  final String? errorMessage;

  CompanyA3SettingsState copyWith({
    bool? isLoading,
    bool? isSaving,
    CompanyA3SettingsModel? settings,
    String? errorMessage,
    bool clearError = false,
  }) {
    return CompanyA3SettingsState(
      isLoading: isLoading ?? this.isLoading,
      isSaving: isSaving ?? this.isSaving,
      settings: settings ?? this.settings,
      errorMessage: clearError ? null : (errorMessage ?? this.errorMessage),
    );
  }
}

final companyA3SettingsControllerProvider = StateNotifierProvider.autoDispose
    .family<
      CompanyA3SettingsController,
      CompanyA3SettingsState,
      CompanyA3Scope
    >((ref, scope) {
      final controller = CompanyA3SettingsController(
        apiClient: ref.read(apiClientProvider),
        token: scope.token,
        companyId: scope.companyId,
      );
      controller.load();
      return controller;
    });

class CompanyA3SettingsController
    extends StateNotifier<CompanyA3SettingsState> {
  CompanyA3SettingsController({
    required ApiClient apiClient,
    required String token,
    required String companyId,
  }) : _apiClient = apiClient,
       _token = token,
       _companyId = companyId,
       super(CompanyA3SettingsState.initial());

  final ApiClient _apiClient;
  final String _token;
  final String _companyId;

  Future<void> load() async {
    state = state.copyWith(isLoading: true, clearError: true);
    try {
      final settings = await _apiClient.getCompanyA3Settings(
        token: _token,
        companyId: _companyId,
      );
      state = state.copyWith(
        isLoading: false,
        settings: settings,
        clearError: true,
      );
    } on ApiException catch (exc) {
      state = state.copyWith(isLoading: false, errorMessage: exc.message);
    }
  }

  Future<bool> save({
    required bool a3Enabled,
    String? a3CompanyCode,
    String? a3ExportPath,
    String? a3ImportMode,
  }) async {
    state = state.copyWith(isSaving: true, clearError: true);
    try {
      final settings = await _apiClient.updateCompanyA3Settings(
        token: _token,
        companyId: _companyId,
        a3Enabled: a3Enabled,
        a3CompanyCode: a3CompanyCode,
        a3ExportPath: a3ExportPath,
        a3ImportMode: a3ImportMode,
      );
      state = state.copyWith(
        isSaving: false,
        settings: settings,
        clearError: true,
      );
      return true;
    } on ApiException catch (exc) {
      state = state.copyWith(isSaving: false, errorMessage: exc.message);
      return false;
    }
  }
}
