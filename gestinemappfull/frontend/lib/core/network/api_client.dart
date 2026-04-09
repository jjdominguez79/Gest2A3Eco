import 'dart:convert';
import 'dart:typed_data';

import 'package:http/http.dart' as http;

import '../config/api_config.dart';
import '../models/accounting_models.dart';
import '../models/company_a3_settings_model.dart';
import '../models/company_model.dart';
import '../models/company_account_model.dart';
import '../models/dashboard_summary_model.dart';
import '../models/document_model.dart';
import '../models/document_ocr_result_model.dart';
import '../models/global_third_party_model.dart';
import '../models/invoice_review_model.dart';
import '../models/invoice_review_pending_item_model.dart';
import '../models/invoice_review_suggestions_model.dart';
import '../models/quick_create_models.dart';
import '../models/user_model.dart';

class ApiException implements Exception {
  ApiException(this.message);

  final String message;
}

class LoginResult {
  const LoginResult({required this.token, required this.user});

  final String token;
  final UserModel user;
}

class ApiClient {
  ApiClient({http.Client? client}) : _client = client ?? http.Client();

  final http.Client _client;

  Future<LoginResult> login({
    required String email,
    required String password,
  }) async {
    final response = await _client.post(
      Uri.parse('${ApiConfig.baseUrl}/auth/login'),
      headers: {'Content-Type': 'application/json'},
      body: jsonEncode({'email': email, 'password': password}),
    );
    final payload = _parseResponse(response);
    return LoginResult(
      token: payload['access_token'] as String,
      user: UserModel.fromJson(payload['user'] as Map<String, dynamic>),
    );
  }

  Future<UserModel> getMe({required String token}) async {
    final response = await _client.get(
      Uri.parse('${ApiConfig.baseUrl}/auth/me'),
      headers: _authHeaders(token),
    );
    final payload = _parseResponse(response);
    return UserModel.fromJson(payload);
  }

  Future<List<CompanyModel>> getCompanies({required String token}) async {
    final response = await _client.get(
      Uri.parse('${ApiConfig.baseUrl}/companies'),
      headers: _authHeaders(token),
    );
    final payload = _parseResponse(response) as List<dynamic>;
    return payload
        .map((item) => CompanyModel.fromJson(item as Map<String, dynamic>))
        .toList();
  }

  Future<CompanyModel> createCompany({
    required String token,
    required String name,
    String? cif,
  }) async {
    final response = await _client.post(
      Uri.parse('${ApiConfig.baseUrl}/companies'),
      headers: {..._authHeaders(token), 'Content-Type': 'application/json'},
      body: jsonEncode({'name': name, 'cif': cif}),
    );
    final payload = _parseResponse(response);
    return CompanyModel.fromJson(payload);
  }

  Future<CompanyA3SettingsModel> getCompanyA3Settings({
    required String token,
    required String companyId,
  }) async {
    final response = await _client.get(
      Uri.parse('${ApiConfig.baseUrl}/companies/$companyId/a3-settings'),
      headers: {..._authHeaders(token), 'X-Company-Id': companyId},
    );
    final payload = _parseResponse(response);
    return CompanyA3SettingsModel.fromJson(payload);
  }

  Future<CompanyA3SettingsModel> updateCompanyA3Settings({
    required String token,
    required String companyId,
    required bool a3Enabled,
    String? a3CompanyCode,
    String? a3ExportPath,
    String? a3ImportMode,
  }) async {
    final response = await _client.put(
      Uri.parse('${ApiConfig.baseUrl}/companies/$companyId/a3-settings'),
      headers: {
        ..._authHeaders(token),
        'X-Company-Id': companyId,
        'Content-Type': 'application/json',
      },
      body: jsonEncode({
        'a3_enabled': a3Enabled,
        'a3_company_code': a3CompanyCode,
        'a3_export_path': a3ExportPath,
        'a3_import_mode': a3ImportMode,
      }),
    );
    final payload = _parseResponse(response);
    return CompanyA3SettingsModel.fromJson(payload);
  }

  Future<DashboardSummaryModel> getDashboardSummary({
    required String token,
    required String companyId,
  }) async {
    final response = await _client.get(
      Uri.parse('${ApiConfig.baseUrl}/dashboard/summary'),
      headers: {..._authHeaders(token), 'X-Company-Id': companyId},
    );
    final payload = _parseResponse(response);
    return DashboardSummaryModel.fromJson(payload);
  }

  Future<List<GlobalThirdPartyModel>> getThirdParties({
    required String token,
    String? taxId,
    String? legalName,
  }) async {
    final uri = Uri.parse('${ApiConfig.baseUrl}/third-parties').replace(
      queryParameters: {
        if (taxId != null && taxId.isNotEmpty) 'tax_id': taxId,
        if (legalName != null && legalName.isNotEmpty) 'legal_name': legalName,
      },
    );
    final response = await _client.get(uri, headers: _authHeaders(token));
    final payload = _parseResponse(response) as List<dynamic>;
    return payload
        .map(
          (item) =>
              GlobalThirdPartyModel.fromJson(item as Map<String, dynamic>),
        )
        .toList();
  }

  Future<GlobalThirdPartyModel> createThirdParty({
    required String token,
    required String thirdPartyType,
    required String legalName,
    String? taxId,
    String? tradeName,
    String? email,
    String? phone,
    String? address,
    String? city,
    String? postalCode,
    String? country,
  }) async {
    final response = await _client.post(
      Uri.parse('${ApiConfig.baseUrl}/third-parties'),
      headers: {..._authHeaders(token), 'Content-Type': 'application/json'},
      body: jsonEncode({
        'third_party_type': thirdPartyType,
        'tax_id': taxId,
        'legal_name': legalName,
        'trade_name': tradeName,
        'email': email,
        'phone': phone,
        'address': address,
        'city': city,
        'postal_code': postalCode,
        'country': country,
      }),
    );
    final payload = _parseResponse(response);
    return GlobalThirdPartyModel.fromJson(payload);
  }

  Future<QuickCreateThirdPartyResult> quickCreateThirdParty({
    required String token,
    required String thirdPartyType,
    required String legalName,
    String? taxId,
    String? tradeName,
    String? documentId,
  }) async {
    final response = await _client.post(
      Uri.parse('${ApiConfig.baseUrl}/third-parties/quick-create'),
      headers: {..._authHeaders(token), 'Content-Type': 'application/json'},
      body: jsonEncode({
        'third_party_type': thirdPartyType,
        'tax_id': taxId,
        'legal_name': legalName,
        'trade_name': tradeName,
        'document_id': documentId,
      }),
    );
    final payload = _parseResponse(response);
    return QuickCreateThirdPartyResult.fromJson(payload);
  }

  Future<List<CompanyAccountModel>> getCompanyAccounts({
    required String token,
    required String companyId,
    String? accountCode,
    String? name,
    String? accountType,
  }) async {
    final uri = Uri.parse('${ApiConfig.baseUrl}/company-accounts').replace(
      queryParameters: {
        if (accountCode != null && accountCode.isNotEmpty)
          'account_code': accountCode,
        if (name != null && name.isNotEmpty) 'name': name,
        if (accountType != null && accountType.isNotEmpty)
          'account_type': accountType,
      },
    );
    final response = await _client.get(
      uri,
      headers: {..._authHeaders(token), 'X-Company-Id': companyId},
    );
    final payload = _parseResponse(response) as List<dynamic>;
    return payload
        .map(
          (item) => CompanyAccountModel.fromJson(item as Map<String, dynamic>),
        )
        .toList();
  }

  Future<CompanyAccountModel> createCompanyAccount({
    required String token,
    required String companyId,
    required String accountCode,
    required String name,
    required String accountType,
    String? globalThirdPartyId,
    String? taxId,
    String? legalName,
    String source = 'manual_app',
    String syncStatus = 'not_synced',
  }) async {
    final response = await _client.post(
      Uri.parse('${ApiConfig.baseUrl}/company-accounts'),
      headers: {
        ..._authHeaders(token),
        'Content-Type': 'application/json',
        'X-Company-Id': companyId,
      },
      body: jsonEncode({
        'account_code': accountCode,
        'name': name,
        'account_type': accountType,
        'global_third_party_id': globalThirdPartyId,
        'tax_id': taxId,
        'legal_name': legalName,
        'source': source,
        'sync_status': syncStatus,
      }),
    );
    final payload = _parseResponse(response);
    return CompanyAccountModel.fromJson(payload);
  }

  Future<QuickCreateCompanyAccountResult> quickCreateCompanyAccount({
    required String token,
    required String companyId,
    required String accountType,
    required String name,
    String? globalThirdPartyId,
    String? taxId,
    String? legalName,
    String? accountCode,
    String? documentId,
  }) async {
    final response = await _client.post(
      Uri.parse('${ApiConfig.baseUrl}/company-accounts/quick-create'),
      headers: {
        ..._authHeaders(token),
        'X-Company-Id': companyId,
        'Content-Type': 'application/json',
      },
      body: jsonEncode({
        'account_type': accountType,
        'name': name,
        'global_third_party_id': globalThirdPartyId,
        'tax_id': taxId,
        'legal_name': legalName,
        'account_code': accountCode,
        'document_id': documentId,
      }),
    );
    final payload = _parseResponse(response);
    return QuickCreateCompanyAccountResult.fromJson(payload);
  }

  Future<String> getNextCompanyAccountCode({
    required String token,
    required String companyId,
    required String accountType,
  }) async {
    final uri = Uri.parse(
      '${ApiConfig.baseUrl}/company-accounts/next-code',
    ).replace(queryParameters: {'account_type': accountType});
    final response = await _client.get(
      uri,
      headers: {..._authHeaders(token), 'X-Company-Id': companyId},
    );
    final payload = _parseResponse(response) as Map<String, dynamic>;
    return payload['next_code'] as String;
  }

  Future<List<DocumentModel>> getDocuments({
    required String token,
    required String companyId,
    String? documentType,
    String? workflowStatus,
    String? originalFilename,
  }) async {
    final uri = Uri.parse('${ApiConfig.baseUrl}/documents').replace(
      queryParameters: {
        if (documentType != null && documentType.isNotEmpty)
          'document_type': documentType,
        if (workflowStatus != null && workflowStatus.isNotEmpty)
          'workflow_status': workflowStatus,
        if (originalFilename != null && originalFilename.isNotEmpty)
          'original_filename': originalFilename,
      },
    );
    final response = await _client.get(
      uri,
      headers: {..._authHeaders(token), 'X-Company-Id': companyId},
    );
    final payload = _parseResponse(response) as List<dynamic>;
    return payload
        .map((item) => DocumentModel.fromJson(item as Map<String, dynamic>))
        .toList();
  }

  Future<DocumentModel> uploadDocument({
    required String token,
    required String companyId,
    required Uint8List bytes,
    required String filename,
  }) async {
    final request = http.MultipartRequest(
      'POST',
      Uri.parse('${ApiConfig.baseUrl}/documents/upload'),
    );
    request.headers.addAll({..._authHeaders(token), 'X-Company-Id': companyId});
    request.files.add(
      http.MultipartFile.fromBytes('file', bytes, filename: filename),
    );
    final streamed = await request.send();
    final response = await http.Response.fromStream(streamed);
    final payload = _parseResponse(response);
    return DocumentModel.fromJson(payload);
  }

  Future<DocumentModel> updateDocument({
    required String token,
    required String companyId,
    required String documentId,
    String? documentType,
    String? workflowStatus,
  }) async {
    final response = await _client.patch(
      Uri.parse('${ApiConfig.baseUrl}/documents/$documentId'),
      headers: {
        ..._authHeaders(token),
        'X-Company-Id': companyId,
        'Content-Type': 'application/json',
      },
      body: jsonEncode({
        if (documentType != null) 'document_type': documentType,
        if (workflowStatus != null) 'workflow_status': workflowStatus,
      }),
    );
    final payload = _parseResponse(response);
    return DocumentModel.fromJson(payload);
  }

  Future<DocumentOcrResultModel> runDocumentOcr({
    required String token,
    required String companyId,
    required String documentId,
  }) async {
    final response = await _client.post(
      Uri.parse('${ApiConfig.baseUrl}/documents/$documentId/run-ocr'),
      headers: {..._authHeaders(token), 'X-Company-Id': companyId},
    );
    final payload = _parseResponse(response);
    return DocumentOcrResultModel.fromJson(payload);
  }

  Future<DocumentOcrResultModel> getDocumentOcrResult({
    required String token,
    required String companyId,
    required String documentId,
  }) async {
    final response = await _client.get(
      Uri.parse('${ApiConfig.baseUrl}/documents/$documentId/ocr-result'),
      headers: {..._authHeaders(token), 'X-Company-Id': companyId},
    );
    final payload = _parseResponse(response);
    return DocumentOcrResultModel.fromJson(payload);
  }

  Future<DocumentModel> classifyDocument({
    required String token,
    required String companyId,
    required String documentId,
    required String documentType,
  }) async {
    final response = await _client.post(
      Uri.parse('${ApiConfig.baseUrl}/documents/$documentId/classify'),
      headers: {
        ..._authHeaders(token),
        'X-Company-Id': companyId,
        'Content-Type': 'application/json',
      },
      body: jsonEncode({'document_type': documentType}),
    );
    final payload = _parseResponse(response);
    return DocumentModel.fromJson(payload);
  }

  Future<List<InvoiceReviewPendingItemModel>> getPendingInvoiceReviews({
    required String token,
    required String companyId,
  }) async {
    final response = await _client.get(
      Uri.parse('${ApiConfig.baseUrl}/invoice-reviews/pending'),
      headers: {..._authHeaders(token), 'X-Company-Id': companyId},
    );
    final payload = _parseResponse(response) as List<dynamic>;
    return payload
        .map(
          (item) => InvoiceReviewPendingItemModel.fromJson(
            item as Map<String, dynamic>,
          ),
        )
        .toList();
  }

  Future<InvoiceReviewModel> getInvoiceReview({
    required String token,
    required String companyId,
    required String documentId,
  }) async {
    final response = await _client.get(
      Uri.parse('${ApiConfig.baseUrl}/invoice-reviews/$documentId'),
      headers: {..._authHeaders(token), 'X-Company-Id': companyId},
    );
    final payload = _parseResponse(response);
    return InvoiceReviewModel.fromJson(payload);
  }

  Future<InvoiceReviewModel> initializeInvoiceReview({
    required String token,
    required String companyId,
    required String documentId,
  }) async {
    final response = await _client.post(
      Uri.parse('${ApiConfig.baseUrl}/invoice-reviews/$documentId/initialize'),
      headers: {..._authHeaders(token), 'X-Company-Id': companyId},
    );
    final payload = _parseResponse(response);
    return InvoiceReviewModel.fromJson(payload);
  }

  Future<InvoiceReviewModel> updateInvoiceReview({
    required String token,
    required String companyId,
    required String documentId,
    String? supplierThirdPartyId,
    String? supplierCompanyAccountId,
    required String supplierNameDetected,
    required String supplierTaxIdDetected,
    required String invoiceNumber,
    String? invoiceDate,
    required String taxableBase,
    required String taxRate,
    required String taxAmount,
    required String totalAmount,
    required String concept,
  }) async {
    final response = await _client.patch(
      Uri.parse('${ApiConfig.baseUrl}/invoice-reviews/$documentId'),
      headers: {
        ..._authHeaders(token),
        'X-Company-Id': companyId,
        'Content-Type': 'application/json',
      },
      body: jsonEncode({
        'supplier_third_party_id': supplierThirdPartyId,
        'supplier_company_account_id': supplierCompanyAccountId,
        'supplier_name_detected': supplierNameDetected,
        'supplier_tax_id_detected': supplierTaxIdDetected,
        'invoice_number': invoiceNumber,
        'invoice_date': invoiceDate,
        'taxable_base': _nullableDouble(taxableBase),
        'tax_rate': _nullableDouble(taxRate),
        'tax_amount': _nullableDouble(taxAmount),
        'total_amount': _nullableDouble(totalAmount),
        'concept': concept,
      }),
    );
    final payload = _parseResponse(response);
    return InvoiceReviewModel.fromJson(payload);
  }

  Future<InvoiceReviewModel> confirmInvoiceReview({
    required String token,
    required String companyId,
    required String documentId,
  }) async {
    final response = await _client.post(
      Uri.parse('${ApiConfig.baseUrl}/invoice-reviews/$documentId/confirm'),
      headers: {..._authHeaders(token), 'X-Company-Id': companyId},
    );
    final payload = _parseResponse(response);
    return InvoiceReviewModel.fromJson(payload);
  }

  Future<InvoiceReviewSuggestionsModel> getInvoiceReviewSuggestions({
    required String token,
    required String companyId,
    required String documentId,
  }) async {
    final response = await _client.get(
      Uri.parse('${ApiConfig.baseUrl}/invoice-reviews/$documentId/suggestions'),
      headers: {..._authHeaders(token), 'X-Company-Id': companyId},
    );
    final payload = _parseResponse(response);
    return InvoiceReviewSuggestionsModel.fromJson(payload);
  }

  Future<List<AccountingPendingItemModel>> getAccountingPending({
    required String token,
    required String companyId,
  }) async {
    final response = await _client.get(
      Uri.parse('${ApiConfig.baseUrl}/accounting/documents/pending'),
      headers: {..._authHeaders(token), 'X-Company-Id': companyId},
    );
    final payload = _parseResponse(response) as List<dynamic>;
    return payload
        .map(
          (item) =>
              AccountingPendingItemModel.fromJson(item as Map<String, dynamic>),
        )
        .toList();
  }

  Future<AccountingBatchModel> createAccountingBatch({
    required String token,
    required String companyId,
    required List<String> documentIds,
    String? notes,
  }) async {
    final response = await _client.post(
      Uri.parse('${ApiConfig.baseUrl}/accounting/batches'),
      headers: {
        ..._authHeaders(token),
        'X-Company-Id': companyId,
        'Content-Type': 'application/json',
      },
      body: jsonEncode({'document_ids': documentIds, 'notes': notes}),
    );
    final payload = _parseResponse(response);
    return AccountingBatchModel.fromJson(payload);
  }

  Future<AccountingBatchModel> generateAccountingBatch({
    required String token,
    required String companyId,
    required String batchId,
    String? notes,
  }) async {
    final response = await _client.post(
      Uri.parse('${ApiConfig.baseUrl}/accounting/batches/$batchId/generate'),
      headers: {
        ..._authHeaders(token),
        'X-Company-Id': companyId,
        'Content-Type': 'application/json',
      },
      body: jsonEncode({'notes': notes}),
    );
    final payload = _parseResponse(response);
    return AccountingBatchModel.fromJson(payload);
  }

  Future<List<AccountingBatchModel>> getAccountingBatches({
    required String token,
    required String companyId,
    String? status,
    String? dateFrom,
    String? dateTo,
  }) async {
    final uri = Uri.parse('${ApiConfig.baseUrl}/accounting/batches').replace(
      queryParameters: {
        if (status != null && status.isNotEmpty) 'status': status,
        if (dateFrom != null && dateFrom.isNotEmpty) 'date_from': dateFrom,
        if (dateTo != null && dateTo.isNotEmpty) 'date_to': dateTo,
      },
    );
    final response = await _client.get(
      uri,
      headers: {..._authHeaders(token), 'X-Company-Id': companyId},
    );
    final payload = _parseResponse(response) as List<dynamic>;
    return payload
        .map(
          (item) => AccountingBatchModel.fromJson(item as Map<String, dynamic>),
        )
        .toList();
  }

  Future<AccountingBatchModel> getAccountingBatch({
    required String token,
    required String companyId,
    required String batchId,
  }) async {
    final response = await _client.get(
      Uri.parse('${ApiConfig.baseUrl}/accounting/batches/$batchId'),
      headers: {..._authHeaders(token), 'X-Company-Id': companyId},
    );
    final payload = _parseResponse(response);
    return AccountingBatchModel.fromJson(payload);
  }

  Future<({Uint8List bytes, String filename})> downloadAccountingBatch({
    required String token,
    required String companyId,
    required String batchId,
  }) async {
    final response = await _client.post(
      Uri.parse('${ApiConfig.baseUrl}/accounting/batches/$batchId/download'),
      headers: {..._authHeaders(token), 'X-Company-Id': companyId},
    );
    if (response.statusCode < 200 || response.statusCode >= 300) {
      final dynamic payload = response.body.isEmpty
          ? <String, dynamic>{}
          : jsonDecode(response.body);
      if (payload is Map<String, dynamic> && payload['detail'] is String) {
        throw ApiException(payload['detail'] as String);
      }
      throw ApiException('Unexpected API error: ${response.statusCode}');
    }
    final disposition = response.headers['content-disposition'] ?? '';
    final filenameMatch = RegExp(
      r'filename=\"?([^\";]+)\"?',
    ).firstMatch(disposition);
    final filename = filenameMatch?.group(1) ?? 'suenlace.dat';
    return (bytes: response.bodyBytes, filename: filename);
  }

  Future<AccountingBatchModel> markAccountingBatchExported({
    required String token,
    required String companyId,
    required String batchId,
    String? notes,
  }) async {
    final response = await _client.post(
      Uri.parse(
        '${ApiConfig.baseUrl}/accounting/batches/$batchId/mark-exported',
      ),
      headers: {
        ..._authHeaders(token),
        'X-Company-Id': companyId,
        'Content-Type': 'application/json',
      },
      body: jsonEncode({'notes': notes}),
    );
    final payload = _parseResponse(response);
    return AccountingBatchModel.fromJson(payload);
  }

  Map<String, String> _authHeaders(String token) {
    return {'Authorization': 'Bearer $token'};
  }

  double? _nullableDouble(String value) {
    final normalized = value.trim().replaceAll(',', '.');
    if (normalized.isEmpty) {
      return null;
    }
    return double.tryParse(normalized);
  }

  dynamic _parseResponse(http.Response response) {
    final dynamic payload = response.body.isEmpty
        ? <String, dynamic>{}
        : jsonDecode(response.body);
    if (response.statusCode >= 200 && response.statusCode < 300) {
      return payload;
    }
    if (payload is Map<String, dynamic> && payload['detail'] is String) {
      throw ApiException(payload['detail'] as String);
    }
    throw ApiException('Unexpected API error: ${response.statusCode}');
  }
}
