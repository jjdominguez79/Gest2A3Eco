import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../auth/presentation/auth_controller.dart';
import '../data/company_profile_repository.dart';
import '../domain/company_profile.dart';
import '../domain/profile_change_request.dart';

final companyProfileRepositoryProvider = Provider((ref) {
  return CompanyProfileRepository(ref.watch(apiClientProvider));
});

final companyProfileProvider = FutureProvider.autoDispose<CompanyProfile>((
  ref,
) {
  return ref.watch(companyProfileRepositoryProvider).getProfile();
});

final profileChangeRequestsProvider =
    FutureProvider.autoDispose<List<ProfileChangeRequest>>((ref) {
      return ref.watch(companyProfileRepositoryProvider).getChangeRequests();
    });
