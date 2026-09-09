class DesktopNotifications {
  bool get supported => false;

  Future<void> initialize({required void Function(String) onClick}) async {}

  Future<void> show({
    required int id,
    required String title,
    required String body,
    required String payload,
  }) async {}

  Future<void> cancel(int id) async {}
}
