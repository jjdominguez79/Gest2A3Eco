class InvoiceReviewSuggestionsModel {
  const InvoiceReviewSuggestionsModel({
    required this.bestThirdPartyId,
    required this.bestCompanyAccountId,
    required this.suggestedThirdParties,
    required this.suggestedCompanyAccounts,
  });

  final String? bestThirdPartyId;
  final String? bestCompanyAccountId;
  final List<SuggestedThirdPartyModel> suggestedThirdParties;
  final List<SuggestedCompanyAccountModel> suggestedCompanyAccounts;

  factory InvoiceReviewSuggestionsModel.fromJson(Map<String, dynamic> json) {
    return InvoiceReviewSuggestionsModel(
      bestThirdPartyId: json['best_third_party_id'] as String?,
      bestCompanyAccountId: json['best_company_account_id'] as String?,
      suggestedThirdParties: (json['suggested_third_parties'] as List<dynamic>)
          .map(
            (item) =>
                SuggestedThirdPartyModel.fromJson(item as Map<String, dynamic>),
          )
          .toList(),
      suggestedCompanyAccounts:
          (json['suggested_company_accounts'] as List<dynamic>)
              .map(
                (item) => SuggestedCompanyAccountModel.fromJson(
                  item as Map<String, dynamic>,
                ),
              )
              .toList(),
    );
  }
}

class SuggestedThirdPartyModel {
  const SuggestedThirdPartyModel({
    required this.id,
    required this.legalName,
    required this.taxId,
    required this.score,
    required this.reason,
  });

  final String id;
  final String legalName;
  final String? taxId;
  final double score;
  final String reason;

  factory SuggestedThirdPartyModel.fromJson(Map<String, dynamic> json) {
    return SuggestedThirdPartyModel(
      id: json['id'] as String,
      legalName: json['legal_name'] as String,
      taxId: json['tax_id'] as String?,
      score: (json['score'] as num).toDouble(),
      reason: json['reason'] as String,
    );
  }
}

class SuggestedCompanyAccountModel {
  const SuggestedCompanyAccountModel({
    required this.id,
    required this.accountCode,
    required this.name,
    required this.taxId,
    required this.globalThirdPartyId,
    required this.score,
    required this.reason,
  });

  final String id;
  final String accountCode;
  final String name;
  final String? taxId;
  final String? globalThirdPartyId;
  final double score;
  final String reason;

  factory SuggestedCompanyAccountModel.fromJson(Map<String, dynamic> json) {
    return SuggestedCompanyAccountModel(
      id: json['id'] as String,
      accountCode: json['account_code'] as String,
      name: json['name'] as String,
      taxId: json['tax_id'] as String?,
      globalThirdPartyId: json['global_third_party_id'] as String?,
      score: (json['score'] as num).toDouble(),
      reason: json['reason'] as String,
    );
  }
}
