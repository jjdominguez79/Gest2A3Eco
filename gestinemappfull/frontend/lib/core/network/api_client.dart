import 'dart:convert';
import 'dart:typed_data';

import 'package:http/http.dart' as http;

import '../config/api_config.dart';
import '../models/company_model.dart';
import '../models/company_account_model.dart';
import '../models/dashboard_summary_model.dart';
import '../models/document_model.dart';
import '../models/global_third_party_model.dart';
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

  Map<String, String> _authHeaders(String token) {
    return {'Authorization': 'Bearer $token'};
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
