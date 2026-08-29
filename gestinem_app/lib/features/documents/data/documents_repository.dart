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
    final params = <String, dynamic>{'offset': offset, 'limit': limit};
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
    return DocumentListResponse.fromJson(response.data as Map<String, dynamic>);
  }

  Future<DocumentListResponse> listAllDocuments({int? fiscalYear}) async {
    const pageSize = 200;
    var offset = 0;
    var total = 0;
    final items = <ClientDocument>[];
    do {
      final page = await listDocuments(
        offset: offset,
        limit: pageSize,
        fiscalYear: fiscalYear,
      );
      total = page.total;
      items.addAll(page.items);
      offset += page.items.length;
      if (page.items.isEmpty) break;
    } while (offset < total);
    return DocumentListResponse(
      items: items,
      total: total,
      offset: 0,
      limit: items.length,
    );
  }

  Future<ClientDocument> getDocument(String id) async {
    final response = await _api.dio.get('/client/documents/$id');
    return ClientDocument.fromJson(response.data as Map<String, dynamic>);
  }

  Future<Uint8List> downloadDocument(String id) async {
    return _api.download('/client/documents/$id/download');
  }

  Future<void> markAsRead(String id) async {
    await _api.dio.post('/client/documents/$id/read');
  }
}
