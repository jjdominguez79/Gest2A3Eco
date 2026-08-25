import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../auth/presentation/auth_controller.dart';
import '../data/documents_repository.dart';
import '../domain/client_document.dart';

final documentsRepositoryProvider = Provider((ref) {
  return DocumentsRepository(ref.watch(apiClientProvider));
});

/// Filtro de ejercicio fiscal activo.
final documentsFiscalYearProvider = StateProvider<int>((ref) {
  return DateTime.now().year;
});

/// Lista de documentos filtrada por ejercicio.
final documentsProvider =
    FutureProvider.autoDispose<DocumentListResponse>((ref) {
  final repo = ref.watch(documentsRepositoryProvider);
  final fiscalYear = ref.watch(documentsFiscalYearProvider);
  return repo.listDocuments(
    fiscalYear: fiscalYear,
    documentType: 'factura',
    limit: 100,
  );
});

/// Detalle de un documento por ID.
final documentDetailProvider =
    FutureProvider.autoDispose.family<ClientDocument, String>((ref, id) {
  return ref.watch(documentsRepositoryProvider).getDocument(id);
});
