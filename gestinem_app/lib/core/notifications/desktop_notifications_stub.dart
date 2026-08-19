class DesktopNotifications {
  bool get supported => false;

  Future<void> initialize() async {}

  Future<void> show({
    required String title,
    required String body,
    required void Function() onClick,
  }) async {}
}
