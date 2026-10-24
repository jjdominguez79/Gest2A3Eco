import 'dart:math';
import 'dart:typed_data';

import 'package:dio/dio.dart';

import '../../../core/api/api_client.dart';
import '../domain/client_invoice.dart';

class InvoicingRepository {
  InvoicingRepository(this._api);

  final ApiClient _api;

  // -- Config --

  Future<Map<String, dynamic>> getConfig() async {
    final resp = await _api.dio.get('/client/invoicing/config');
    return resp.data as Map<String, dynamic>;
  }

  // -- Customers --

  Future<List<InvoiceCustomer>> listCustomers() async {
    final resp = await _api.dio.get('/client/invoicing/customers');
    return (resp.data as List<dynamic>)
        .map((e) => InvoiceCustomer.fromJson(e as Map<String, dynamic>))
        .toList();
  }

  Future<InvoiceCustomer> createCustomer(Map<String, dynamic> data) async {
    final resp = await _api.dio.post('/client/invoicing/customers', data: data);
    return InvoiceCustomer.fromJson(resp.data as Map<String, dynamic>);
  }

  // -- Drafts --

  Future<List<ClientInvoice>> listDrafts() async {
    final resp = await _api.dio.get('/client/invoicing/drafts');
    return (resp.data as List<dynamic>)
        .map((e) => ClientInvoice.fromJson(e as Map<String, dynamic>))
        .toList();
  }

  Future<ClientInvoice> createDraft(Map<String, dynamic> data) async {
    final resp = await _api.dio.post('/client/invoicing/drafts', data: data);
    return ClientInvoice.fromJson(resp.data as Map<String, dynamic>);
  }

  Future<ClientInvoice> getDraft(String id) async {
    final resp = await _api.dio.get('/client/invoicing/drafts/$id');
    return ClientInvoice.fromJson(resp.data as Map<String, dynamic>);
  }

  Future<ClientInvoice> updateDraft(
    String id,
    Map<String, dynamic> data,
  ) async {
    final resp = await _api.dio.put('/client/invoicing/drafts/$id', data: data);
    return ClientInvoice.fromJson(resp.data as Map<String, dynamic>);
  }

  Future<void> deleteDraft(String id) async {
    await _api.dio.delete('/client/invoicing/drafts/$id');
  }

  Future<ClientInvoice> issueDraft(String id) async {
    final idempotencyKey =
        '${DateTime.now().millisecondsSinceEpoch}-${Random().nextInt(999999)}';
    final resp = await _api.dio.post(
      '/client/invoicing/drafts/$id/issue',
      options: Options(headers: {'Idempotency-Key': idempotencyKey}),
    );
    return ClientInvoice.fromJson(resp.data as Map<String, dynamic>);
  }

  // -- Invoices --

  Future<Map<String, dynamic>> listInvoices({
    int offset = 0,
    int limit = 50,
    int? fiscalYear,
    String? status,
  }) async {
    final params = <String, dynamic>{'offset': offset, 'limit': limit};
    if (fiscalYear != null && fiscalYear > 0) {
      params['fiscal_year'] = fiscalYear;
    }
    if (status != null && status.isNotEmpty) {
      params['status'] = status;
    }
    final resp = await _api.dio.get(
      '/client/invoicing/invoices',
      queryParameters: params,
    );
    return resp.data as Map<String, dynamic>;
  }

  Future<ClientInvoice> getInvoice(String id) async {
    final resp = await _api.dio.get('/client/invoicing/invoices/$id');
    return ClientInvoice.fromJson(resp.data as Map<String, dynamic>);
  }

  Future<Uint8List> downloadInvoicePdf(String id) async {
    return _api.download('/client/invoicing/invoices/$id/pdf');
  }

  /// Crea una factura rectificativa que referencia a [id]. La original
  /// nunca se edita (seccion 15: una factura emitida no se modifica).
  Future<ClientInvoice> rectifyInvoice(
    String id, {
    required String reason,
    required List<Map<String, dynamic>> lines,
  }) async {
    final idempotencyKey =
        '${DateTime.now().millisecondsSinceEpoch}-${Random().nextInt(999999)}';
    final resp = await _api.dio.post(
      '/client/invoicing/invoices/$id/rectify',
      data: {'reason': reason, 'lines': lines},
      options: Options(headers: {'Idempotency-Key': idempotencyKey}),
    );
    return ClientInvoice.fromJson(resp.data as Map<String, dynamic>);
  }

  /// Registra la anulacion fiscal de la factura [id]. No borra ni modifica
  /// los datos originales.
  Future<ClientInvoice> cancelInvoice(String id, {required String reason}) async {
    final resp = await _api.dio.post(
      '/client/invoicing/invoices/$id/cancel',
      data: {'reason': reason},
    );
    return ClientInvoice.fromJson(resp.data as Map<String, dynamic>);
  }

  // -- Catalogo de productos y servicios --

  Future<Map<String, dynamic>> listCatalogItems({
    String q = '',
    bool? active,
    int offset = 0,
    int limit = 50,
  }) async {
    final params = <String, dynamic>{'offset': offset, 'limit': limit};
    if (q.isNotEmpty) params['q'] = q;
    if (active != null) params['active'] = active;
    final resp = await _api.dio.get(
      '/client/invoicing/catalog/items',
      queryParameters: params,
    );
    return resp.data as Map<String, dynamic>;
  }

  Future<CatalogItem> getCatalogItem(String id) async {
    final resp = await _api.dio.get('/client/invoicing/catalog/items/$id');
    return CatalogItem.fromJson(resp.data as Map<String, dynamic>);
  }

  Future<CatalogItem> createCatalogItem(Map<String, dynamic> data) async {
    final resp = await _api.dio.post(
      '/client/invoicing/catalog/items',
      data: data,
    );
    return CatalogItem.fromJson(resp.data as Map<String, dynamic>);
  }

  Future<CatalogItem> updateCatalogItem(
    String id,
    Map<String, dynamic> data,
  ) async {
    final resp = await _api.dio.put(
      '/client/invoicing/catalog/items/$id',
      data: data,
    );
    return CatalogItem.fromJson(resp.data as Map<String, dynamic>);
  }

  Future<void> deactivateCatalogItem(String id) async {
    await _api.dio.delete('/client/invoicing/catalog/items/$id');
  }
}
