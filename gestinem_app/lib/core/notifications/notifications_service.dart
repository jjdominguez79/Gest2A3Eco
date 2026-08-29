import 'dart:async';
import 'dart:convert';

import 'package:flutter/foundation.dart';
import 'package:firebase_core/firebase_core.dart';
import 'package:firebase_messaging/firebase_messaging.dart';
import 'package:flutter_local_notifications/flutter_local_notifications.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:package_info_plus/package_info_plus.dart';
import 'package:dio/dio.dart';

import '../api/api_client.dart';
import '../../features/auth/domain/user_profile.dart';
import '../../firebase_options.dart';
import 'desktop_notifications.dart';

// Clave publica VAPID para FCM Web. Se inyecta en el build con:
//   --dart-define=FIREBASE_WEB_VAPID_KEY=<clave>
const _kVapidKey = String.fromEnvironment('FIREBASE_WEB_VAPID_KEY');

const _androidChannel = AndroidNotificationChannel(
  'gestinem_messages',
  'Mensajes',
  description: 'Avisos de nuevos mensajes de Gestinem',
  importance: Importance.high,
);

String notificationTargetType(Map<String, dynamic> data) {
  final explicit = data['target_type']?.toString() ?? '';
  if (explicit.isNotEmpty) return explicit;
  return (data['thread_id']?.toString() ?? '').isNotEmpty
      ? 'internal_thread'
      : 'conversation';
}

String notificationTargetId(Map<String, dynamic> data) {
  final explicit = data['target_id']?.toString() ?? '';
  if (explicit.isNotEmpty) return explicit;
  return notificationTargetType(data) == 'internal_thread'
      ? data['thread_id']?.toString() ?? ''
      : data['conversation_id']?.toString() ?? '';
}

@visibleForTesting
int notificationIdForTarget(String targetType, String targetId) {
  var hash = 0x811c9dc5;
  for (final unit in '$targetType:$targetId'.codeUnits) {
    hash ^= unit;
    hash = (hash * 0x01000193) & 0x7fffffff;
  }
  return hash;
}

Future<void> _showAndroidMessage(
  RemoteMessage message, {
  FlutterLocalNotificationsPlugin? configuredPlugin,
}) async {
  final data = message.data;
  final targetId = notificationTargetId(data);
  if (targetId.isEmpty) return;
  final plugin = configuredPlugin ?? FlutterLocalNotificationsPlugin();
  if (configuredPlugin == null) {
    await plugin.initialize(
      settings: const InitializationSettings(
        android: AndroidInitializationSettings('@mipmap/ic_launcher'),
      ),
    );
  }
  final android = plugin
      .resolvePlatformSpecificImplementation<
        AndroidFlutterLocalNotificationsPlugin
      >();
  await android?.createNotificationChannel(_androidChannel);
  await plugin.show(
    id: notificationIdForTarget(notificationTargetType(data), targetId),
    title:
        data['title']?.toString() ??
        message.notification?.title ??
        'Nuevo mensaje de Gestinem',
    body:
        data['body']?.toString() ??
        message.notification?.body ??
        'Tienes un nuevo mensaje',
    notificationDetails: const NotificationDetails(
      android: AndroidNotificationDetails(
        'gestinem_messages',
        'Mensajes',
        channelDescription: 'Avisos de nuevos mensajes de Gestinem',
        importance: Importance.high,
        priority: Priority.high,
        icon: '@mipmap/ic_launcher',
      ),
    ),
    payload: jsonEncode(data),
  );
}

@pragma('vm:entry-point')
Future<void> firebaseMessagingBackgroundHandler(RemoteMessage message) async {
  if (Firebase.apps.isEmpty) await Firebase.initializeApp();
  await _showAndroidMessage(message);
}

void configureFirebaseBackgroundMessaging() {
  if (!kIsWeb && defaultTargetPlatform == TargetPlatform.android) {
    FirebaseMessaging.onBackgroundMessage(firebaseMessagingBackgroundHandler);
  }
}

final notificationsServiceProvider = Provider<NotificationsService>(
  (ref) => NotificationsService(),
);

/// Estado del permiso de notificacion del dispositivo/navegador.
enum NotificationPermissionState {
  /// Permiso no solicitado todavia.
  available,

  /// Solicitud en curso.
  pending,

  /// Permiso concedido y token FCM registrado.
  authorized,

  /// El usuario ha denegado el permiso.
  denied,

  /// Firebase no esta configurado (valores PENDIENTE o VAPID ausente en Web).
  configError,
}

class NotificationEvent {
  const NotificationEvent({
    required this.conversationId,
    required this.opened,
    this.threadId,
    this.documentId,
    this.title,
    this.body,
  });

  final String conversationId;
  final String? threadId;
  final String? documentId;
  final bool opened;
  final String? title;
  final String? body;
}

class NotificationsService {
  final DesktopNotifications _desktop = DesktopNotifications();
  final FlutterLocalNotificationsPlugin _local =
      FlutterLocalNotificationsPlugin();
  String? _owner;
  String? _deviceId;
  AuthSession? _session;
  ApiClient? _api;
  NotificationEvent? _pendingOpenedEvent;
  StreamSubscription<String>? _tokenRefresh;
  final _events = StreamController<NotificationEvent>.broadcast();

  // Guardas para evitar inicializacion concurrente o duplicada.
  bool _initializing = false;
  bool _messageListenersConfigured = false;
  bool _localNotificationsConfigured = false;
  bool _fcmConfigured = false;

  NotificationPermissionState _permissionState =
      NotificationPermissionState.available;

  Stream<NotificationEvent> get events => _events.stream;

  NotificationEvent? takePendingOpenedEvent() {
    final event = _pendingOpenedEvent;
    _pendingOpenedEvent = null;
    return event;
  }

  /// Estado actual del permiso de notificacion.
  NotificationPermissionState get permissionState => _permissionState;

  /// True si Firebase esta inicializado y el token FCM esta registrado.
  bool get fcmConfigured => _fcmConfigured;

  Future<void> _ensureFirebaseInitialized() async {
    if (Firebase.apps.isNotEmpty) return;

    if (kIsWeb) {
      await Firebase.initializeApp(options: DefaultFirebaseOptions.web);
    } else {
      // Android utiliza android/app/google-services.json.
      await Firebase.initializeApp();
    }
  }

  /// Inicializa el servicio para la sesion activa.
  ///
  /// En Android solicita permiso y registra el token de inmediato.
  /// En Web NO abre el dialogo del navegador; usa [activateWebNotifications]
  /// desde la UI para el consentimiento explicito.
  Future<void> initialize(AuthSession session, ApiClient api) async {
    _session = session;
    _api = api;
    if (_desktop.supported) {
      if (_owner == _ownerFor(session)) return;
      try {
        await _desktop.initialize();
        _owner = _ownerFor(session);
      } catch (error, stackTrace) {
        debugPrint(
          'No se pudieron activar las notificaciones de Windows: '
          '$error\n$stackTrace',
        );
      }
      return;
    }

    if (!_supported || _owner == _ownerFor(session)) return;

    // Proteccion contra inicializacion concurrente.
    if (_initializing) return;
    _initializing = true;

    try {
      if (Firebase.apps.isEmpty) {
        await _ensureFirebaseInitialized();
      }
      final messaging = FirebaseMessaging.instance;
      await _configureMessageListeners(messaging);

      if (kIsWeb) {
        // En Web: comprobar si el permiso ya estaba concedido y registrar token.
        // No llamamos a requestPermission() aqui; eso lo hace el usuario
        // explicitamente desde WebNotificationPermissionBanner.
        final settings = await messaging.getNotificationSettings();
        if (settings.authorizationStatus == AuthorizationStatus.authorized) {
          await _registerWebToken(session, api, messaging);
          _permissionState = NotificationPermissionState.authorized;
          _fcmConfigured = true;
        }
      } else {
        // Android / iOS / macOS: flujo habitual.
        await _configureLocalNotifications();
        await messaging.requestPermission();
        final token = await messaging.getToken();
        if (token != null) {
          await _register(session, api, token);
          _permissionState = NotificationPermissionState.authorized;
          _fcmConfigured = true;
        }
      }

      _owner = _ownerFor(session);
      await _tokenRefresh?.cancel();
      _tokenRefresh = messaging.onTokenRefresh.listen(
        (refreshed) => unawaited(_register(session, api, refreshed)),
      );
    } catch (error, stackTrace) {
      // Firebase es opcional en desarrollo.
      debugPrint(
        'No se pudieron activar las notificaciones: $error\n$stackTrace',
      );
    } finally {
      _initializing = false;
    }
  }

  /// Solicita el permiso del navegador y registra el token FCM.
  ///
  /// Solo para Web. Devuelve [true] si el permiso fue concedido.
  /// Debe llamarse desde un gesto explicito del usuario.
  Future<bool> activateWebNotifications(
    AuthSession session,
    ApiClient api,
  ) async {
    _permissionState = NotificationPermissionState.pending;
    try {
      if (Firebase.apps.isEmpty) {
        await _ensureFirebaseInitialized();
      }
      final messaging = FirebaseMessaging.instance;
      await _configureMessageListeners(messaging);

      final settings = await messaging.requestPermission();
      if (settings.authorizationStatus != AuthorizationStatus.authorized) {
        _permissionState = NotificationPermissionState.denied;
        return false;
      }
      await _registerWebToken(session, api, messaging);
      _owner = _ownerFor(session);
      await _tokenRefresh?.cancel();
      _tokenRefresh = messaging.onTokenRefresh.listen(
        (refreshed) => unawaited(_register(session, api, refreshed)),
      );
      _permissionState = NotificationPermissionState.authorized;
      _fcmConfigured = true;
      return true;
    } catch (error, stackTrace) {
      debugPrint('No se pudo activar la notificacion web: $error\n$stackTrace');
      _permissionState = NotificationPermissionState.configError;
      return false;
    }
  }

  Future<void> showDesktop({
    required String title,
    required String body,
    required void Function() onClick,
  }) async {
    try {
      await _desktop.show(title: title, body: body, onClick: onClick);
    } catch (error, stackTrace) {
      debugPrint(
        'No se pudo mostrar la notificacion de Windows: $error\n$stackTrace',
      );
    }
  }

  Future<void> _configureMessageListeners(FirebaseMessaging messaging) async {
    if (_messageListenersConfigured) return;
    _messageListenersConfigured = true;

    FirebaseMessaging.onMessage.listen((message) {
      // En Web la aplicacion esta visible: el WebSocket ya entrega el mensaje.
      // Suprimimos el evento FCM de primer plano para evitar duplicados.
      if (kIsWeb) return;
      _emit(message, opened: false);
      unawaited(_showForegroundNotification(message));
    });
    FirebaseMessaging.onMessageOpenedApp.listen(
      (message) => _emit(message, opened: true),
    );
    final initial = await messaging.getInitialMessage();
    if (initial != null) _emit(initial, opened: true);
  }

  Future<void> _configureLocalNotifications() async {
    if (_localNotificationsConfigured ||
        defaultTargetPlatform != TargetPlatform.android) {
      return;
    }
    _localNotificationsConfigured = true;
    await _local.initialize(
      settings: const InitializationSettings(
        android: AndroidInitializationSettings('@mipmap/ic_launcher'),
      ),
      onDidReceiveNotificationResponse: (response) {
        final payload = response.payload;
        if (payload == null || payload.isEmpty) return;
        try {
          final data = jsonDecode(payload) as Map<String, dynamic>;
          _emitData(data, opened: true);
        } catch (error, stackTrace) {
          debugPrint('No se pudo abrir la notificacion: $error\n$stackTrace');
        }
      },
    );
    final android = _local
        .resolvePlatformSpecificImplementation<
          AndroidFlutterLocalNotificationsPlugin
        >();
    await android?.createNotificationChannel(_androidChannel);
    await android?.requestNotificationsPermission();
    final launch = await _local.getNotificationAppLaunchDetails();
    final payload = launch?.notificationResponse?.payload;
    if (launch?.didNotificationLaunchApp == true &&
        payload != null &&
        payload.isNotEmpty) {
      try {
        _emitData(jsonDecode(payload) as Map<String, dynamic>, opened: true);
      } catch (error, stackTrace) {
        debugPrint(
          'No se pudo recuperar la notificacion inicial: '
          '$error\n$stackTrace',
        );
      }
    }
  }

  Future<void> _showForegroundNotification(RemoteMessage message) async {
    if (defaultTargetPlatform != TargetPlatform.android) return;
    if (!await _isStillUnread(message.data)) return;
    await _showAndroidMessage(message, configuredPlugin: _local);
  }

  Future<bool> _isStillUnread(Map<String, dynamic> data) async {
    final session = _session;
    final api = _api;
    if (session == null || api == null) return true;
    final targetType = notificationTargetType(data);
    final targetId = notificationTargetId(data);
    try {
      if (targetType == 'document') {
        final response = await api.dio.get<Map<String, dynamic>>(
          '/client/documents/$targetId',
        );
        return response.data?['is_read'] != true;
      }
      final path = targetType == 'internal_thread'
          ? '/staff/internal/threads'
          : '/${session.profile.type.name}/conversations';
      final response = await api.dio.get<List<dynamic>>(path);
      final item = response.data?.cast<Map<String, dynamic>>().where(
        (row) => row['id']?.toString() == targetId,
      );
      return item != null &&
          item.isNotEmpty &&
          (item.first['unread_count'] as num? ?? 0) > 0;
    } catch (_) {
      return true;
    }
  }

  Future<void> _registerWebToken(
    AuthSession session,
    ApiClient api,
    FirebaseMessaging messaging,
  ) async {
    final vapidKey = _kVapidKey.isNotEmpty ? _kVapidKey : null;
    final token = await messaging.getToken(vapidKey: vapidKey);
    if (token != null) await _register(session, api, token);
  }

  void _emit(RemoteMessage message, {required bool opened}) {
    _emitData(
      message.data,
      opened: opened,
      title: message.notification?.title,
      body: message.notification?.body,
    );
  }

  void _emitData(
    Map<String, dynamic> data, {
    required bool opened,
    String? title,
    String? body,
  }) {
    final targetType = notificationTargetType(data);
    final targetId = notificationTargetId(data);
    final conversationId = targetType == 'conversation' ? targetId : '';
    final threadId = targetType == 'internal_thread' ? targetId : null;
    final documentId = targetType == 'document' ? targetId : null;
    if (conversationId.isEmpty &&
        (threadId == null || threadId.isEmpty) &&
        (documentId == null || documentId.isEmpty)) {
      return;
    }
    final event = NotificationEvent(
      conversationId: conversationId,
      threadId: threadId,
      documentId: documentId,
      opened: opened,
      title: title ?? data['title']?.toString(),
      body: body ?? data['body']?.toString(),
    );
    if (opened) _pendingOpenedEvent = event;
    _events.add(event);
  }

  Future<void> setActiveTarget(String targetType, String targetId) async {
    final session = _session;
    final api = _api;
    final deviceId = _deviceId;
    if (session == null || api == null || deviceId == null) return;
    await api.dio.patch<void>(
      '/${session.profile.type.name}/app-devices/$deviceId/presence',
      data: FormData.fromMap({
        'target_type': targetType,
        'target_id': targetId,
      }),
    );
  }

  Future<void> clearActiveTarget() => setActiveTarget('', '');

  Future<void> cancelTarget(String targetType, String targetId) async {
    if (defaultTargetPlatform != TargetPlatform.android ||
        targetId.isEmpty ||
        !_localNotificationsConfigured) {
      return;
    }
    await _local.cancel(id: notificationIdForTarget(targetType, targetId));
  }

  Future<void> unregister(AuthSession session, ApiClient api) async {
    final deviceId = _deviceId;
    if (deviceId != null && _owner == _ownerFor(session)) {
      await api.dio.delete<void>(
        '/${session.profile.type.name}/app-devices/$deviceId',
      );
    }
    await _tokenRefresh?.cancel();
    _tokenRefresh = null;
    _owner = null;
    _deviceId = null;
    _session = null;
    _api = null;
    _pendingOpenedEvent = null;
    _fcmConfigured = false;
    _permissionState = NotificationPermissionState.available;
  }

  Future<void> _register(
    AuthSession session,
    ApiClient api,
    String token,
  ) async {
    final packageInfo = await PackageInfo.fromPlatform();
    final response = await api.dio.put<Map<String, dynamic>>(
      '/${session.profile.type.name}/app-devices',
      data: {
        'platform': _platform,
        'push_token': token,
        'device_name': '',
        'app_version': '${packageInfo.version}+${packageInfo.buildNumber}',
      },
    );
    _deviceId = response.data?['id'] as String?;
  }

  String _ownerFor(AuthSession session) =>
      '${session.profile.type.name}:${session.profile.id}';

  bool get _supported =>
      kIsWeb ||
      defaultTargetPlatform == TargetPlatform.android ||
      defaultTargetPlatform == TargetPlatform.iOS ||
      defaultTargetPlatform == TargetPlatform.macOS;

  String get _platform => kIsWeb
      ? 'web'
      : switch (defaultTargetPlatform) {
          TargetPlatform.android => 'android',
          TargetPlatform.iOS => 'ios',
          TargetPlatform.macOS => 'macos',
          _ => throw UnsupportedError('Plataforma sin FCM'),
        };
}
