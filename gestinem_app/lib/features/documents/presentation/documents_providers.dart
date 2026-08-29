import 'dart:typed_data';

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

/// Lista completa de documentos del ejercicio para construir sus carpetas.
final documentsProvider = FutureProvider.autoDispose<DocumentListResponse>((
  ref,
) {
  final repo = ref.watch(documentsRepositoryProvider);
  final fiscalYear = ref.watch(documentsFiscalYearProvider);
  return repo.listAllDocuments(fiscalYear: fiscalYear);
});

final documentBytesProvider = FutureProvider.autoDispose
    .family<Uint8List, String>((ref, id) {
      return ref.watch(documentsRepositoryProvider).downloadDocument(id);
    });

/// Detalle de un documento por ID.
final documentDetailProvider = FutureProvider.autoDispose
    .family<ClientDocument, String>((ref, id) {
      return ref.watch(documentsRepositoryProvider).getDocument(id);
    });

/// Marca como leido al abrir el detalle y refresca los indicadores de nuevo.
final documentReadProvider = FutureProvider.autoDispose.family<void, String>((
  ref,
  id,
) async {
  await ref.watch(documentsRepositoryProvider).markAsRead(id);
  ref.invalidate(documentsProvider);
});
