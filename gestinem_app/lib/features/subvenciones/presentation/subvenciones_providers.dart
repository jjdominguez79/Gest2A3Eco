import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../auth/presentation/auth_controller.dart';
import '../data/subvenciones_repository.dart';
import '../domain/subvencion.dart';

final subvencionesRepositoryProvider = Provider<SubvencionesRepository>((ref) {
  return SubvencionesRepository(ref.watch(apiClientProvider));
});

final subvencionesParaMiProvider = StateProvider<bool>((ref) => true);
final subvencionesConsultaProvider = StateProvider<String>((ref) => '');

final subvencionesProvider = FutureProvider.autoDispose<ListaSubvenciones>((
  ref,
) {
  return ref
      .watch(subvencionesRepositoryProvider)
      .listar(
        paraMi: ref.watch(subvencionesParaMiProvider),
        consulta: ref.watch(subvencionesConsultaProvider),
      );
});

final subvencionProvider = FutureProvider.autoDispose
    .family<Subvencion, String>(
      (ref, codigo) =>
          ref.watch(subvencionesRepositoryProvider).detalle(codigo),
    );

final preferenciasSubvencionesProvider =
    FutureProvider.autoDispose<PreferenciasSubvenciones>(
      (ref) => ref.watch(subvencionesRepositoryProvider).preferencias(),
    );

final territoriosConsultaProvider = StateProvider<String>((ref) => '');

final territoriosSubvencionesProvider =
    FutureProvider.autoDispose<List<TerritorioSubvencion>>(
      (ref) => ref
          .watch(subvencionesRepositoryProvider)
          .territorios(consulta: ref.watch(territoriosConsultaProvider)),
    );
