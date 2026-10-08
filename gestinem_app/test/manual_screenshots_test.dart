import 'dart:io';
import 'dart:typed_data';

import 'package:dio/dio.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:gestinem/core/api/api_client.dart';
import 'package:gestinem/core/notifications/notifications_service.dart';
import 'package:gestinem/core/websocket/realtime_service.dart';
import 'package:gestinem/features/auth/domain/user_profile.dart';
import 'package:gestinem/features/auth/presentation/auth_controller.dart';
import 'package:gestinem/features/certificates/domain/certificate_request.dart';
import 'package:gestinem/features/certificates/presentation/certificates_providers.dart';
import 'package:gestinem/features/company_profile/domain/company_profile.dart';
import 'package:gestinem/features/company_profile/presentation/company_profile_providers.dart';
import 'package:gestinem/features/documents/presentation/documentation_screen.dart';
import 'package:gestinem/features/messaging/domain/conversation.dart';
import 'package:gestinem/features/messaging/domain/message.dart';
import 'package:gestinem/features/messaging/presentation/conversation_screen.dart';
import 'package:gestinem/features/messaging/presentation/conversations_screen.dart';
import 'package:gestinem/features/messaging/presentation/messaging_providers.dart';
import 'package:gestinem/features/platform/features_provider.dart';
import 'package:gestinem/features/profile/presentation/profile_screen.dart';

import 'test_helpers.dart';

class _FakeRealtime extends RealtimeService {
  @override
  Future<void> connect(AuthSession session, ApiClient api) async {}
}

class _FakeNotifications extends NotificationsService {
  @override
  Future<void> initialize(AuthSession session, ApiClient api) async {}
}

final _canales = [
  Conversation(
    id: 'general',
    companyCode: 'E00006',
    companyName: 'Empresa Demo, S.L.',
    kind: 'general',
    channelLabel: 'Canal general',
    state: 'activo',
    unreadCount: 0,
    updatedAt: DateTime(2026, 10, 8, 10, 35),
  ),
  Conversation(
    id: 'private',
    companyCode: 'E00006',
    companyName: 'Empresa Demo, S.L.',
    kind: 'private',
    channelLabel: 'Tu asesor',
    state: 'activo',
    unreadCount: 1,
    updatedAt: DateTime(2026, 10, 8, 10, 42),
  ),
];

final _mensajes = [
  Message(
    id: 'm1',
    conversationId: 'general',
    authorType: 'staff',
    authorId: 'staff-1',
    authorName: 'Gestinem',
    authorAvatarUrl: '',
    body: 'Buenos días. Ya tiene disponible el resumen trimestral.',
    createdAt: DateTime(2026, 10, 8, 10, 20),
    deleted: false,
  ),
  Message(
    id: 'm2',
    conversationId: 'general',
    authorType: 'client',
    authorId: 'client-1',
    authorName: 'Cliente Prueba',
    authorAvatarUrl: '',
    body: 'Gracias. Adjunto también la factura pendiente.',
    createdAt: DateTime(2026, 10, 8, 10, 24),
    deleted: false,
    estadoEnvio: 'sent',
  ),
  Message(
    id: 'm3',
    conversationId: 'general',
    authorType: 'staff',
    authorId: 'staff-1',
    authorName: 'Gestinem',
    authorAvatarUrl: '',
    body: 'Recibido, muchas gracias.',
    createdAt: DateTime(2026, 10, 8, 10, 28),
    deleted: false,
    reactions: const [MessageReaction(emoji: '👍', count: 1, mine: true)],
  ),
];

const _empresa = CompanyProfile(
  companyCode: 'E00006',
  name: 'Empresa Demo, S.L.',
  legalName: 'Empresa Demo, S.L.',
  taxId: 'B12345678',
  address: 'Calle Principal, 12',
  postalCode: '28001',
  city: 'Madrid',
  province: 'Madrid',
  country: 'España',
  phone: '910 000 000',
  email: 'empresa@ejemplo.es',
);

ThemeData _tema() => ThemeData(
  fontFamily: 'Roboto',
  textTheme: Typography.material2021(platform: TargetPlatform.android).black
      .apply(
        fontFamily: 'Roboto',
        fontFamilyFallback: const ['Segoe UI Emoji'],
      ),
  colorScheme: ColorScheme.fromSeed(
    seedColor: const Color(0xFF004B76),
    primary: const Color(0xFF004B76),
    secondary: const Color(0xFF1B91CF),
    surface: const Color(0xFFF8FAFC),
  ),
  scaffoldBackgroundColor: const Color(0xFFF2F6F8),
  useMaterial3: true,
  inputDecorationTheme: const InputDecorationTheme(
    border: OutlineInputBorder(),
    filled: true,
    fillColor: Colors.white,
  ),
  cardTheme: const CardThemeData(elevation: 0, margin: EdgeInsets.zero),
);

Directory _materialFontsDirectory() {
  var current = File(Platform.resolvedExecutable).parent;
  while (current.parent.path != current.path) {
    final candidate = Directory(
      '${current.path}${Platform.pathSeparator}bin${Platform.pathSeparator}'
      'cache${Platform.pathSeparator}artifacts${Platform.pathSeparator}'
      'material_fonts',
    );
    if (candidate.existsSync()) return candidate;
    current = current.parent;
  }
  throw StateError('No se localizaron las fuentes incluidas con Flutter.');
}

List<Override> _baseOverrides() => [
  sessionProvider.overrideWith((ref) => FakeSessionController(ref)),
  apiClientProvider.overrideWithValue(
    ApiClient(
      dio: Dio(BaseOptions(baseUrl: 'https://example.test'))
        ..httpClientAdapter = JsonAdapter(<String, dynamic>{}),
      tokenProvider: () => testSession.token,
    ),
  ),
  realtimeServiceProvider.overrideWithValue(_FakeRealtime()),
  notificationsServiceProvider.overrideWithValue(_FakeNotifications()),
  conversationsProvider.overrideWith((ref) async => _canales),
  messagesProvider.overrideWith(
    (ref, id) async => id == 'general' ? _mensajes : [],
  ),
  platformFeaturesProvider.overrideWith(
    (ref) async => const PlatformFeatures(
      documents: true,
      certificates: true,
      invoicing: true,
      subsidies: true,
    ),
  ),
  companyProfileProvider.overrideWith((ref) async => _empresa),
  profileChangeRequestsProvider.overrideWith((ref) async => const []),
  sendWithEnterProvider.overrideWith((ref) async => false),
];

Widget _app(Widget home, {List<Override> extraOverrides = const []}) =>
    ProviderScope(
      overrides: [..._baseOverrides(), ...extraOverrides],
      child: MaterialApp(
        debugShowCheckedModeBanner: false,
        theme: _tema(),
        home: home,
      ),
    );

Future<void> _prepararPantalla(WidgetTester tester) async {
  await tester.binding.setSurfaceSize(const Size(390, 900));
  tester.view.devicePixelRatio = 1;
  addTearDown(() async {
    tester.view.resetDevicePixelRatio();
    await tester.binding.setSurfaceSize(null);
  });
}

Future<void> _capturar(WidgetTester tester, String nombre) async {
  await expectLater(
    find.byType(MaterialApp),
    matchesGoldenFile('goldens/manual/$nombre.png'),
  );
}

void main() {
  const recordChannel = MethodChannel('com.llfbandit.record/messages');

  setUpAll(() async {
    if (!Platform.isWindows) return;
    final materialFonts = _materialFontsDirectory();
    final fonts = FontLoader('Roboto')
      ..addFont(
        Future.value(
          ByteData.sublistView(
            File(
              '${materialFonts.path}${Platform.pathSeparator}roboto-regular.ttf',
            ).readAsBytesSync(),
          ),
        ),
      )
      ..addFont(
        Future.value(
          ByteData.sublistView(
            File(
              '${materialFonts.path}${Platform.pathSeparator}roboto-medium.ttf',
            ).readAsBytesSync(),
          ),
        ),
      )
      ..addFont(
        Future.value(
          ByteData.sublistView(
            File(
              '${materialFonts.path}${Platform.pathSeparator}roboto-bold.ttf',
            ).readAsBytesSync(),
          ),
        ),
      );
    await fonts.load();
    final icons = FontLoader('MaterialIcons')
      ..addFont(
        Future.value(
          ByteData.sublistView(
            File(
              '${materialFonts.path}${Platform.pathSeparator}materialicons-regular.otf',
            ).readAsBytesSync(),
          ),
        ),
      );
    await icons.load();
    final emojis = FontLoader('Segoe UI Emoji')
      ..addFont(
        Future.value(
          ByteData.sublistView(
            File(r'C:\Windows\Fonts\seguiemj.ttf').readAsBytesSync(),
          ),
        ),
      );
    await emojis.load();
    TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger
        .setMockMethodCallHandler(recordChannel, (call) async => null);
  });

  tearDownAll(() {
    if (!Platform.isWindows) return;
    TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger
        .setMockMethodCallHandler(recordChannel, null);
  });

  testWidgets('captura la conversación del cliente', (tester) async {
    await _prepararPantalla(tester);
    await tester.pumpWidget(_app(const ConversationsScreen()));
    await tester.pumpAndSettle();
    await _capturar(tester, '01_conversacion');
  }, skip: !Platform.isWindows);

  testWidgets('captura el menú principal del cliente', (tester) async {
    await _prepararPantalla(tester);
    await tester.pumpWidget(_app(const ConversationsScreen()));
    await tester.pumpAndSettle();
    await tester.tap(find.byIcon(Icons.menu));
    await tester.pumpAndSettle();
    await _capturar(tester, '02_menu');
  }, skip: !Platform.isWindows);

  testWidgets('captura las opciones del botón más', (tester) async {
    await _prepararPantalla(tester);
    await tester.pumpWidget(
      _app(const ConversationScreen(conversationId: 'general')),
    );
    await tester.pumpAndSettle();
    final compact = find.byKey(const Key('composer-more-actions'));
    final amplio = find.byKey(const Key('attach-files'));
    await tester.tap(compact.evaluate().isNotEmpty ? compact : amplio);
    await tester.pumpAndSettle();
    await _capturar(tester, '03_adjuntar');
  }, skip: !Platform.isWindows);

  testWidgets('captura las acciones de un mensaje', (tester) async {
    await _prepararPantalla(tester);
    await tester.pumpWidget(_app(const ConversationsScreen()));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Recibido, muchas gracias.'));
    await tester.pumpAndSettle();
    await _capturar(tester, '04_acciones_mensaje');
  }, skip: !Platform.isWindows);

  testWidgets('captura la pantalla de documentación', (tester) async {
    await _prepararPantalla(tester);
    await tester.pumpWidget(
      _app(
        const DocumentationScreen(),
        extraOverrides: [
          certificateStatusProvider.overrideWith(
            (ref) async =>
                const CertificateStatus(configured: true, status: 'valid'),
          ),
        ],
      ),
    );
    await tester.pumpAndSettle();
    await _capturar(tester, '05_documentacion');
  }, skip: !Platform.isWindows);

  testWidgets('captura Mi área', (tester) async {
    await _prepararPantalla(tester);
    await tester.pumpWidget(_app(const ProfileScreen()));
    await tester.pumpAndSettle();
    await _capturar(tester, '06_mi_area');
  }, skip: !Platform.isWindows);
}
