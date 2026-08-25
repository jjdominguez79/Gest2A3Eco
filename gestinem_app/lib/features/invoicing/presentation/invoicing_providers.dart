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

final invoiceDraftsProvider =
    FutureProvider.autoDispose<List<ClientInvoice>>((ref) {
  return ref.watch(invoicingRepositoryProvider).listDrafts();
});

final invoiceDetailProvider =
    FutureProvider.autoDispose.family<ClientInvoice, String>((ref, id) {
  return ref.watch(invoicingRepositoryProvider).getInvoice(id);
});

final draftDetailProvider =
    FutureProvider.autoDispose.family<ClientInvoice, String>((ref, id) {
  return ref.watch(invoicingRepositoryProvider).getDraft(id);
});
