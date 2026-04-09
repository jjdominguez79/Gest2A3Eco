import 'dart:typed_data';

import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../core/models/accounting_models.dart';
import '../../../core/network/api_client.dart';
import '../../../core/state/session_controller.dart';

class AccountingScope {
  const AccountingScope({
    required this.token,
    required this.companyId,
    required this.companyName,
  });

  final String token;
  final String companyId;
  final String companyName;
}

class AccountingState {
  static const _sentinel = Object();

  const AccountingState({
    required this.isLoading,
    required this.isGenerating,
    required this.isDownloading,
    required this.isMarkingExported,
    required this.pendingItems,
    required this.batches,
    required this.selectedBatch,
    required this.selectedDocumentIds,
    required this.statusFilter,
    required this.dateFrom,
    required this.dateTo,
    required this.errorMessage,
  });

  factory AccountingState.initial() {
    return const AccountingState(
      isLoading: true,
      isGenerating: false,
      isDownloading: false,
      isMarkingExported: false,
      pendingItems: [],
      batches: [],
      selectedBatch: null,
      selectedDocumentIds: {},
      statusFilter: null,
      dateFrom: null,
      dateTo: null,
      errorMessage: null,
    );
  }

  final bool isLoading;
  final bool isGenerating;
  final bool isDownloading;
  final bool isMarkingExported;
  final List<AccountingPendingItemModel> pendingItems;
  final List<AccountingBatchModel> batches;
  final AccountingBatchModel? selectedBatch;
  final Set<String> selectedDocumentIds;
  final String? statusFilter;
  final DateTime? dateFrom;
  final DateTime? dateTo;
  final String? errorMessage;

  AccountingState copyWith({
    bool? isLoading,
    bool? isGenerating,
    bool? isDownloading,
    bool? isMarkingExported,
    List<AccountingPendingItemModel>? pendingItems,
    List<AccountingBatchModel>? batches,
    Object? selectedBatch = _sentinel,
    Set<String>? selectedDocumentIds,
    Object? statusFilter = _sentinel,
    Object? dateFrom = _sentinel,
    Object? dateTo = _sentinel,
    String? errorMessage,
    bool clearError = false,
  }) {
    return AccountingState(
      isLoading: isLoading ?? this.isLoading,
      isGenerating: isGenerating ?? this.isGenerating,
      isDownloading: isDownloading ?? this.isDownloading,
      isMarkingExported: isMarkingExported ?? this.isMarkingExported,
      pendingItems: pendingItems ?? this.pendingItems,
      batches: batches ?? this.batches,
      selectedBatch: identical(selectedBatch, _sentinel)
          ? this.selectedBatch
          : selectedBatch as AccountingBatchModel?,
      selectedDocumentIds: selectedDocumentIds ?? this.selectedDocumentIds,
      statusFilter: identical(statusFilter, _sentinel)
          ? this.statusFilter
          : statusFilter as String?,
      dateFrom: identical(dateFrom, _sentinel)
          ? this.dateFrom
          : dateFrom as DateTime?,
      dateTo: identical(dateTo, _sentinel) ? this.dateTo : dateTo as DateTime?,
      errorMessage: clearError ? null : (errorMessage ?? this.errorMessage),
    );
  }
}

final accountingControllerProvider = StateNotifierProvider.autoDispose
    .family<AccountingController, AccountingState, AccountingScope>((
      ref,
      scope,
    ) {
      final controller = AccountingController(
        apiClient: ref.read(apiClientProvider),
        token: scope.token,
        companyId: scope.companyId,
      );
      controller.load();
      return controller;
    });

class AccountingController extends StateNotifier<AccountingState> {
  AccountingController({
    required ApiClient apiClient,
    required String token,
    required String companyId,
  }) : _apiClient = apiClient,
       _token = token,
       _companyId = companyId,
       super(AccountingState.initial());

  final ApiClient _apiClient;
  final String _token;
  final String _companyId;

  Future<void> load({String? preserveSelectedBatchId}) async {
    state = state.copyWith(isLoading: true, clearError: true);
    try {
      final pending = await _apiClient.getAccountingPending(
        token: _token,
        companyId: _companyId,
      );
      final batches = await _apiClient.getAccountingBatches(
        token: _token,
        companyId: _companyId,
        status: state.statusFilter,
        dateFrom: _formatDate(state.dateFrom),
        dateTo: _formatDate(state.dateTo),
      );
      final selectedBatchId =
          preserveSelectedBatchId ??
          state.selectedBatch?.id ??
          (batches.isEmpty ? null : batches.first.id);
      AccountingBatchModel? selectedBatch;
      if (selectedBatchId != null &&
          batches.any((batch) => batch.id == selectedBatchId)) {
        selectedBatch = await _apiClient.getAccountingBatch(
          token: _token,
          companyId: _companyId,
          batchId: selectedBatchId,
        );
      }
      state = state.copyWith(
        isLoading: false,
        pendingItems: pending,
        batches: batches,
        selectedBatch: selectedBatch,
        selectedDocumentIds: state.selectedDocumentIds
            .where((id) => pending.any((item) => item.documentId == id))
            .toSet(),
        clearError: true,
      );
    } on ApiException catch (exc) {
      state = state.copyWith(isLoading: false, errorMessage: exc.message);
    }
  }

  void toggleDocumentSelection(String documentId, bool value) {
    final next = Set<String>.from(state.selectedDocumentIds);
    if (value) {
      next.add(documentId);
    } else {
      next.remove(documentId);
    }
    state = state.copyWith(selectedDocumentIds: next);
  }

  void clearSelection() {
    state = state.copyWith(selectedDocumentIds: <String>{});
  }

  Future<void> setStatusFilter(String? value) async {
    state = state.copyWith(statusFilter: value, selectedBatch: null);
    await load();
  }

  Future<void> setDateRange(DateTime? from, DateTime? to) async {
    state = state.copyWith(dateFrom: from, dateTo: to, selectedBatch: null);
    await load();
  }

  Future<void> openBatch(String batchId) async {
    try {
      final batch = await _apiClient.getAccountingBatch(
        token: _token,
        companyId: _companyId,
        batchId: batchId,
      );
      state = state.copyWith(selectedBatch: batch, clearError: true);
    } on ApiException catch (exc) {
      state = state.copyWith(errorMessage: exc.message);
    }
  }

  Future<AccountingBatchModel?> generateBatchFromSelection({
    String? notes,
  }) async {
    if (state.selectedDocumentIds.isEmpty) {
      state = state.copyWith(errorMessage: 'Selecciona al menos una factura.');
      return null;
    }
    state = state.copyWith(isGenerating: true, clearError: true);
    try {
      final draft = await _apiClient.createAccountingBatch(
        token: _token,
        companyId: _companyId,
        documentIds: state.selectedDocumentIds.toList(),
        notes: notes,
      );
      final batch = await _apiClient.generateAccountingBatch(
        token: _token,
        companyId: _companyId,
        batchId: draft.id,
        notes: notes,
      );
      state = state.copyWith(
        isGenerating: false,
        selectedDocumentIds: <String>{},
      );
      await load(preserveSelectedBatchId: batch.id);
      return batch;
    } on ApiException catch (exc) {
      state = state.copyWith(isGenerating: false, errorMessage: exc.message);
      return null;
    }
  }

  Future<({Uint8List bytes, String filename})?> downloadSelectedBatch() async {
    final batch = state.selectedBatch;
    if (batch == null) {
      return null;
    }
    state = state.copyWith(isDownloading: true, clearError: true);
    try {
      final file = await _apiClient.downloadAccountingBatch(
        token: _token,
        companyId: _companyId,
        batchId: batch.id,
      );
      state = state.copyWith(isDownloading: false);
      await load(preserveSelectedBatchId: batch.id);
      return file;
    } on ApiException catch (exc) {
      state = state.copyWith(isDownloading: false, errorMessage: exc.message);
      return null;
    }
  }

  Future<AccountingBatchModel?> markSelectedBatchExported({
    String? notes,
  }) async {
    final batch = state.selectedBatch;
    if (batch == null) {
      return null;
    }
    state = state.copyWith(isMarkingExported: true, clearError: true);
    try {
      final updated = await _apiClient.markAccountingBatchExported(
        token: _token,
        companyId: _companyId,
        batchId: batch.id,
        notes: notes,
      );
      state = state.copyWith(isMarkingExported: false);
      await load(preserveSelectedBatchId: updated.id);
      return updated;
    } on ApiException catch (exc) {
      state = state.copyWith(
        isMarkingExported: false,
        errorMessage: exc.message,
      );
      return null;
    }
  }

  String? _formatDate(DateTime? value) {
    if (value == null) {
      return null;
    }
    final month = value.month.toString().padLeft(2, '0');
    final day = value.day.toString().padLeft(2, '0');
    return '${value.year}-$month-$day';
  }
}
