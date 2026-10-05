import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../auth/presentation/auth_controller.dart';
import '../data/subvenciones_admin_repository.dart';
import '../domain/subvencion.dart';

class FiltrosSubvencionesAdmin {
  const FiltrosSubvencionesAdmin({
    this.consulta = '',
    this.estado = 'en_vigor',
    this.visibilidad = 'visibles',
    this.fuente = '',
    this.pagina = 0,
  });

  final String consulta;
  final String estado;
  final String visibilidad;
  final String fuente;
  final int pagina;

  FiltrosSubvencionesAdmin copyWith({
    String? consulta,
    String? estado,
    String? visibilidad,
    String? fuente,
    int? pagina,
  }) => FiltrosSubvencionesAdmin(
    consulta: consulta ?? this.consulta,
    estado: estado ?? this.estado,
    visibilidad: visibilidad ?? this.visibilidad,
    fuente: fuente ?? this.fuente,
    pagina: pagina ?? this.pagina,
  );
}

final subvencionesAdminRepositoryProvider =
    Provider<SubvencionesAdminRepository>(
      (ref) => SubvencionesAdminRepository(ref.watch(apiClientProvider)),
    );

final filtrosSubvencionesAdminProvider =
    StateProvider<FiltrosSubvencionesAdmin>(
      (ref) => const FiltrosSubvencionesAdmin(),
    );

final dashboardSubvencionesAdminProvider =
    FutureProvider.autoDispose<DashboardSubvencionesAdmin>(
      (ref) => ref.watch(subvencionesAdminRepositoryProvider).dashboard(),
    );

final listaSubvencionesAdminProvider =
    FutureProvider.autoDispose<ListaSubvenciones>((ref) {
      final filters = ref.watch(filtrosSubvencionesAdminProvider);
      return ref
          .watch(subvencionesAdminRepositoryProvider)
          .listar(
            consulta: filters.consulta,
            estado: filters.estado,
            visibilidad: filters.visibilidad,
            fuente: filters.fuente,
            pagina: filters.pagina,
          );
    });

final subvencionAdminProvider = FutureProvider.autoDispose
    .family<Subvencion, String>(
      (ref, codigo) =>
          ref.watch(subvencionesAdminRepositoryProvider).detalle(codigo),
    );
