import 'dart:typed_data';

import '../../../core/api/api_client.dart';
import '../domain/client_document.dart';

class DocumentsRepository {
  DocumentsRepository(this._api);

  final ApiClient _api;

  Future<DocumentListResponse> listDocuments({
    int offset = 0,
    int limit = 50,
    String? documentType,
    int? fiscalYear,
  }) async {
    final params = <String, dynamic>{
      'offset': offset,
      'limit': limit,
    };
    if (documentType != null && documentType.isNotEmpty) {
      params['document_type'] = documentType;
    }
    if (fiscalYear != null && fiscalYear > 0) {
      params['fiscal_year'] = fiscalYear;
    }
    final response = await _api.dio.get(
      '/client/documents/',
      queryParameters: params,
    );
    return DocumentListResponse.fromJson(
      response.data as Map<String, dynamic>,
    );
  }

  Future<ClientDocument> getDocument(String id) async {
    final response = await _api.dio.get('/client/documents/$id');
    return ClientDocument.fromJson(
      response.data as Map<String, dynamic>,
    );
  }

  Future<Uint8List> downloadDocument(String id) async {
    return _api.download('/client/documents/$id/download');
  }

  Future<void> markAsRead(String id) async {
    await _api.dio.post('/client/documents/$id/read');
  }
}
