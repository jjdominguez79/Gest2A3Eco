class AppConfig {
  const AppConfig({
    required this.apiBaseUrl,
    required this.webSocketUrl,
    required this.environment,
  });

  factory AppConfig.fromEnvironment() {
    const root = String.fromEnvironment(
      'API_BASE_URL',
      defaultValue: 'http://localhost:8000',
    );
    const explicitWebSocket = String.fromEnvironment('WEBSOCKET_URL');
    const environment = String.fromEnvironment(
      'ENVIRONMENT',
      defaultValue: 'development',
    );
    final normalized = root.replaceAll(RegExp(r'/+$'), '');
    final socketRoot = explicitWebSocket.isNotEmpty
        ? explicitWebSocket.replaceAll(RegExp(r'/+$'), '')
        : normalized.replaceFirst(RegExp(r'^http'), 'ws');
    return AppConfig(
      apiBaseUrl: '$normalized/api/v1/messaging',
      webSocketUrl: '$socketRoot/api/v1/messaging/ws',
      environment: environment,
    );
  }

  final String apiBaseUrl;
  final String webSocketUrl;
  final String environment;
}

final appConfig = AppConfig.fromEnvironment();
