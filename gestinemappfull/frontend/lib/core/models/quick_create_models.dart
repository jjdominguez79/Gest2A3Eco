import 'company_account_model.dart';
import 'global_third_party_model.dart';

class QuickCreateThirdPartyResult {
  const QuickCreateThirdPartyResult({required this.item, required this.reused});

  final GlobalThirdPartyModel item;
  final bool reused;

  factory QuickCreateThirdPartyResult.fromJson(Map<String, dynamic> json) {
    return QuickCreateThirdPartyResult(
      item: GlobalThirdPartyModel.fromJson(
        json['item'] as Map<String, dynamic>,
      ),
      reused: json['reused'] as bool,
    );
  }
}

class QuickCreateCompanyAccountResult {
  const QuickCreateCompanyAccountResult({
    required this.item,
    required this.proposedAccountCode,
    required this.reused,
  });

  final CompanyAccountModel item;
  final String proposedAccountCode;
  final bool reused;

  factory QuickCreateCompanyAccountResult.fromJson(Map<String, dynamic> json) {
    return QuickCreateCompanyAccountResult(
      item: CompanyAccountModel.fromJson(json['item'] as Map<String, dynamic>),
      proposedAccountCode: json['proposed_account_code'] as String,
      reused: json['reused'] as bool,
    );
  }
}
