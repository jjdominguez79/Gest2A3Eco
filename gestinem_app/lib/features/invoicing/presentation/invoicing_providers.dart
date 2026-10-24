import 'dart:typed_data';

import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../auth/presentation/auth_controller.dart';
import '../data/invoicing_repository.dart';
import '../domain/client_invoice.dart';

final invoicingRepositoryProvider = Provider((ref) {
  return InvoicingRepository(ref.watch(apiClientProvider));
});

final invoicingConfigProvider =
    FutureProvider.autoDispose<Map<String, dynamic>>((ref) {
      return ref.watch(invoicingRepositoryProvider).getConfig();
    });

final invoiceCustomersProvider =
    FutureProvider.autoDispose<List<InvoiceCustomer>>((ref) {
      return ref.watch(invoicingRepositoryProvider).listCustomers();
    });

final invoiceDraftsProvider = FutureProvider.autoDispose<List<ClientInvoice>>((
  ref,
) {
  return ref.watch(invoicingRepositoryProvider).listDrafts();
});

final invoiceDetailProvider = FutureProvider.autoDispose
    .family<ClientInvoice, String>((ref, id) {
      return ref.watch(invoicingRepositoryProvider).getInvoice(id);
    });

final draftDetailProvider = FutureProvider.autoDispose
    .family<ClientInvoice, String>((ref, id) {
      return ref.watch(invoicingRepositoryProvider).getDraft(id);
    });

/// Filtros de la pestana de facturas emitidas (seccion 19: filtros por
/// ejercicio, serie, cliente y estado).
class InvoiceListFilters {
  const InvoiceListFilters({this.fiscalYear, this.status});

  final int? fiscalYear;
  final String? status;

  InvoiceListFilters copyWith({
    int? fiscalYear,
    bool clearFiscalYear = false,
    String? status,
    bool clearStatus = false,
  }) {
    return InvoiceListFilters(
      fiscalYear: clearFiscalYear ? null : (fiscalYear ?? this.fiscalYear),
      status: clearStatus ? null : (status ?? this.status),
    );
  }
}

final invoiceListFiltersProvider =
    StateProvider.autoDispose<InvoiceListFilters>(
      (ref) => const InvoiceListFilters(),
    );

final invoiceListProvider = FutureProvider.autoDispose<Map<String, dynamic>>((
  ref,
) {
  final filters = ref.watch(invoiceListFiltersProvider);
  return ref
      .watch(invoicingRepositoryProvider)
      .listInvoices(fiscalYear: filters.fiscalYear, status: filters.status);
});

final invoicePdfBytesProvider = FutureProvider.autoDispose
    .family<Uint8List, String>((ref, id) {
      return ref.watch(invoicingRepositoryProvider).downloadInvoicePdf(id);
    });

// -- Catalogo --

final catalogSearchProvider = StateProvider.autoDispose<String>((ref) => '');

final catalogItemsProvider = FutureProvider.autoDispose<List<CatalogItem>>((
  ref,
) async {
  final q = ref.watch(catalogSearchProvider);
  final result = await ref
      .watch(invoicingRepositoryProvider)
      .listCatalogItems(q: q, active: true, limit: 200);
  return (result['items'] as List<dynamic>)
      .map((e) => CatalogItem.fromJson(e as Map<String, dynamic>))
      .toList();
});

final catalogItemDetailProvider = FutureProvider.autoDispose
    .family<CatalogItem, String>((ref, id) {
      return ref.watch(invoicingRepositoryProvider).getCatalogItem(id);
    });
