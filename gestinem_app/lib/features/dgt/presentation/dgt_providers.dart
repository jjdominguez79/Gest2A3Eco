import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../auth/presentation/auth_controller.dart';
import '../data/dgt_repository.dart';
import '../domain/dgt_expediente.dart';

final dgtRepositoryProvider = Provider<DgtRepository>(
  (ref) => DgtRepository(ref.watch(apiClientProvider)),
);

final expedientesDgtProvider = FutureProvider.autoDispose<List<DgtExpediente>>(
  (ref) => ref.watch(dgtRepositoryProvider).listar(),
);
