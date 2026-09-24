enum AppUpdateRequirement { disabled, current, optional, mandatory }

class AppUpdatePolicy {
  const AppUpdatePolicy({
    required this.platform,
    required this.enabled,
    required this.latestVersion,
    required this.latestBuild,
    required this.minimumBuild,
    required this.storeUrl,
  });

  factory AppUpdatePolicy.fromJson(Map<String, dynamic> json) {
    final rawStoreUrl = json['store_url']?.toString().trim() ?? '';
    final parsedStoreUrl = Uri.tryParse(rawStoreUrl);
    return AppUpdatePolicy(
      platform: json['platform']?.toString().trim().toLowerCase() ?? '',
      enabled: json['enabled'] == true,
      latestVersion: json['latest_version']?.toString().trim() ?? '',
      latestBuild: _positiveInt(json['latest_build']),
      minimumBuild: _positiveInt(json['minimum_build']),
      storeUrl:
          parsedStoreUrl != null &&
              parsedStoreUrl.hasScheme &&
              {'https', 'http', 'itms-apps'}.contains(parsedStoreUrl.scheme)
          ? parsedStoreUrl
          : null,
    );
  }

  final String platform;
  final bool enabled;
  final String latestVersion;
  final int latestBuild;
  final int minimumBuild;
  final Uri? storeUrl;

  AppUpdateRequirement requirementFor(int installedBuild) {
    if (!enabled || storeUrl == null) return AppUpdateRequirement.disabled;
    if (installedBuild < minimumBuild) {
      return AppUpdateRequirement.mandatory;
    }
    if (installedBuild < latestBuild) return AppUpdateRequirement.optional;
    return AppUpdateRequirement.current;
  }
}

int _positiveInt(Object? value) {
  final parsed = value is int ? value : int.tryParse(value?.toString() ?? '');
  return parsed != null && parsed > 0 ? parsed : 1;
}
