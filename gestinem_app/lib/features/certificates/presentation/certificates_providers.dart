import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../auth/presentation/auth_controller.dart';
import '../data/certificates_repository.dart';
import '../domain/certificate_request.dart';

final certificatesRepositoryProvider = Provider<CertificatesRepository>((ref) {
  return CertificatesRepository(ref.watch(apiClientProvider));
});

final certificateTypesProvider =
    FutureProvider.autoDispose<List<CertificateType>>((ref) {
      return ref.watch(certificatesRepositoryProvider).listTypes();
    });

final certificateStatusProvider = FutureProvider.autoDispose<CertificateStatus>(
  (ref) {
    return ref.watch(certificatesRepositoryProvider).getStatus();
  },
);

final certificateRequestsProvider =
    FutureProvider.autoDispose<List<CertificateRequest>>((ref) {
      return ref.watch(certificatesRepositoryProvider).listRequests();
    });

final staffCertificateTypesProvider = FutureProvider.autoDispose
    .family<List<CertificateType>, String>((ref, companyCode) {
      return ref
          .watch(certificatesRepositoryProvider)
          .listTypes(companyCode: companyCode);
    });

final staffCertificateStatusProvider = FutureProvider.autoDispose
    .family<CertificateStatus, String>((ref, companyCode) {
      return ref
          .watch(certificatesRepositoryProvider)
          .getStatus(companyCode: companyCode);
    });

final staffCertificateRequestsProvider = FutureProvider.autoDispose
    .family<List<CertificateRequest>, String>((ref, companyCode) {
      return ref
          .watch(certificatesRepositoryProvider)
          .listRequests(companyCode: companyCode);
    });
