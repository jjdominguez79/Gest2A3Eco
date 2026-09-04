import 'dart:math';

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
  }) async {
    final params = <String, dynamic>{'offset': offset, 'limit': limit};
    if (fiscalYear != null && fiscalYear > 0) {
      params['fiscal_year'] = fiscalYear;
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
}
