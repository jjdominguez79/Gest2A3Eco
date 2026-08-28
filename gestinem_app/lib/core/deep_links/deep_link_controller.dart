import 'dart:async';

import 'package:app_links/app_links.dart';
import 'package:flutter/foundation.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

final deepLinkProvider = StateNotifierProvider<DeepLinkController, Uri?>((ref) {
  return DeepLinkController();
});

class DeepLinkController extends StateNotifier<Uri?> {
  DeepLinkController({AppLinks? appLinks})
    : _appLinks = appLinks ?? AppLinks(),
      super(null) {
    unawaited(_start());
  }

  final AppLinks _appLinks;
  StreamSubscription<Uri>? _subscription;

  Future<void> _start() async {
    try {
      final initial = await _appLinks.getInitialLink();
      _accept(initial);
      _subscription = _appLinks.uriLinkStream.listen(
        _accept,
        onError: (Object error) =>
            debugPrint('Deep link no disponible: $error'),
      );
    } catch (error) {
      debugPrint('Deep link no disponible: $error');
    }
  }

  void _accept(Uri? uri) {
    if (routeForDeepLink(uri) != null) state = uri;
  }

  void clear() => state = null;

  @override
  void dispose() {
    unawaited(_subscription?.cancel());
    super.dispose();
  }
}

String? routeForDeepLink(Uri? uri) {
  if (uri == null || uri.scheme != 'es.gestinem.app' || uri.host != 'auth') {
    return null;
  }
  final action = uri.pathSegments.isEmpty ? null : uri.pathSegments.first;
  final token =
      uri.queryParameters['token'] ??
      uri.queryParameters['invite'] ??
      uri.queryParameters['reset'];
  if (token == null || token.isEmpty) return null;
  final encoded = Uri.encodeQueryComponent(token);
  return switch (action) {
    'invite' => '/accept-invite?token=$encoded',
    'reset' => '/reset-password?token=$encoded',
    _ => null,
  };
}
