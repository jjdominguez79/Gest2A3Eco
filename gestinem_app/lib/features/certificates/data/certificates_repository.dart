import 'dart:typed_data';

import '../../../core/api/api_client.dart';
import '../domain/certificate_request.dart';

class CertificatesRepository {
  CertificatesRepository(this._api);

  final ApiClient _api;

  String _basePath(String? companyCode) => companyCode == null
      ? '/client/certificates'
      : '/client/certificates/staff/organizations/${Uri.encodeComponent(companyCode)}';

  Future<List<CertificateType>> listTypes({String? companyCode}) async {
    final response = await _api.dio.get('${_basePath(companyCode)}/types');
    final data = response.data as Map<String, dynamic>;
    return (data['items'] as List<dynamic>? ?? const [])
        .map((item) => CertificateType.fromJson(item as Map<String, dynamic>))
        .toList();
  }

  Future<CertificateStatus> getStatus({String? companyCode}) async {
    final response = await _api.dio.get(
      '${_basePath(companyCode)}/certificate-status',
    );
    return CertificateStatus.fromJson(response.data as Map<String, dynamic>);
  }

  Future<List<CertificateRequest>> listRequests({String? companyCode}) async {
    final response = await _api.dio.get('${_basePath(companyCode)}/requests');
    final data = response.data as Map<String, dynamic>;
    return (data['items'] as List<dynamic>? ?? const [])
        .map(
          (item) => CertificateRequest.fromJson(item as Map<String, dynamic>),
        )
        .toList();
  }

  Future<CertificateRequest> create(
    String certificateType, {
    Map<String, dynamic> parameters = const {},
    String? companyCode,
  }) async {
    final response = await _api.dio.post(
      '${_basePath(companyCode)}/requests',
      data: {
        'certificate_type': certificateType,
        'parameters': parameters,
        'idempotency_key': DateTime.now().microsecondsSinceEpoch.toString(),
      },
    );
    return CertificateRequest.fromJson(response.data as Map<String, dynamic>);
  }

  Future<CertificateRequest> cancel(
    String requestId, {
    String? companyCode,
  }) async {
    final response = await _api.dio.post(
      '${_basePath(companyCode)}/requests/$requestId/cancel',
    );
    return CertificateRequest.fromJson(response.data as Map<String, dynamic>);
  }

  Future<CertificateRequest> retry(
    String requestId, {
    String? companyCode,
  }) async {
    final response = await _api.dio.post(
      '${_basePath(companyCode)}/requests/$requestId/retry',
    );
    return CertificateRequest.fromJson(response.data as Map<String, dynamic>);
  }

  Future<void> remove(String requestId, {String? companyCode}) async {
    await _api.dio.delete('${_basePath(companyCode)}/requests/$requestId');
  }

  Future<Uint8List> downloadRequestDocument(
    String requestId, {
    required String companyCode,
    bool receipt = false,
  }) {
    return _api.download(
      '${_basePath(companyCode)}/requests/$requestId/document'
      '${receipt ? '?kind=receipt' : ''}',
    );
  }

  Future<CertificateRequest> publishRequestDocument(
    String requestId, {
    required String companyCode,
  }) async {
    final response = await _api.dio.post(
      '${_basePath(companyCode)}/requests/$requestId/publish',
    );
    return CertificateRequest.fromJson(response.data as Map<String, dynamic>);
  }
}
