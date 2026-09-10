import '../../../core/api/api_client.dart';
import '../domain/certificate_request.dart';

class CertificatesRepository {
  CertificatesRepository(this._api);

  final ApiClient _api;

  Future<List<CertificateType>> listTypes() async {
    final response = await _api.dio.get('/client/certificates/types');
    final data = response.data as Map<String, dynamic>;
    return (data['items'] as List<dynamic>? ?? const [])
        .map((item) => CertificateType.fromJson(item as Map<String, dynamic>))
        .toList();
  }

  Future<CertificateStatus> getStatus() async {
    final response = await _api.dio.get(
      '/client/certificates/certificate-status',
    );
    return CertificateStatus.fromJson(response.data as Map<String, dynamic>);
  }

  Future<List<CertificateRequest>> listRequests() async {
    final response = await _api.dio.get('/client/certificates/requests');
    final data = response.data as Map<String, dynamic>;
    return (data['items'] as List<dynamic>? ?? const [])
        .map(
          (item) => CertificateRequest.fromJson(item as Map<String, dynamic>),
        )
        .toList();
  }

  Future<CertificateRequest> create(String certificateType) async {
    final response = await _api.dio.post(
      '/client/certificates/requests',
      data: {
        'certificate_type': certificateType,
        'parameters': <String, dynamic>{},
        'idempotency_key': DateTime.now().microsecondsSinceEpoch.toString(),
      },
    );
    return CertificateRequest.fromJson(response.data as Map<String, dynamic>);
  }

  Future<CertificateRequest> cancel(String requestId) async {
    final response = await _api.dio.post(
      '/client/certificates/requests/$requestId/cancel',
    );
    return CertificateRequest.fromJson(response.data as Map<String, dynamic>);
  }
}
