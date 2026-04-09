import 'dart:convert';

import 'package:http/http.dart' as http;

import '../config/api_config.dart';
import '../models/company_model.dart';
import '../models/dashboard_summary_model.dart';
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
