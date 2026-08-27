import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../auth/presentation/auth_controller.dart';

/// Estado de las funciones disponibles para el cliente.
class PlatformFeatures {
  const PlatformFeatures({
    this.companyProfile = true,
    this.documents = false,
    this.invoicing = false,
  });

  final bool companyProfile;
  final bool documents;
  final bool invoicing;

  factory PlatformFeatures.fromJson(Map<String, dynamic> json) {
    return PlatformFeatures(
      companyProfile: json['company_profile'] as bool? ?? true,
      documents: json['documents'] as bool? ?? false,
      invoicing: json['invoicing'] as bool? ?? false,
    );
  }
}

final platformFeaturesProvider =
    FutureProvider.autoDispose<PlatformFeatures>((ref) async {
  final api = ref.watch(apiClientProvider);
  try {
    final resp = await api.dio.get('/client/features');
    return PlatformFeatures.fromJson(resp.data as Map<String, dynamic>);
  } catch (_) {
    // Si falla (staff user o error), devolver solo perfil visible.
    return const PlatformFeatures();
  }
});
