import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:go_router/go_router.dart';
import 'package:gestinem/features/auth/presentation/auth_controller.dart';
import 'package:gestinem/features/platform/features_provider.dart';
import 'package:gestinem/app/router.dart';
import 'package:gestinem/features/documents/domain/client_document.dart';
import 'package:gestinem/features/documents/presentation/documents_providers.dart';

import 'test_helpers.dart';

// ---------------------------------------------------------------------------
// Los tests instancian el routerProvider REAL via ProviderScope con overrides.
// No se copia la logica de redireccion en funciones auxiliares de test.
//
// Las pantallas de destino (ConversationsScreen, InvoicingScreen, etc.) tienen
// dependencias de red. Los errores de build de esas pantallas se suprimen para
// poder verificar la URI a la que el router redirige.
// ---------------------------------------------------------------------------

/// Suprime errores de build de widgets durante un test.
/// Devuelve la funcion de restauracion que debe llamarse en addTearDown.
VoidCallback _suppressBuildErrors() {
  final prev = FlutterError.onError;
  FlutterError.onError = (details) {
    final lib = details.library ?? '';
    if (lib.contains('widget') || lib.contains('render')) return;
    prev?.call(details);
  };
  return () => FlutterError.onError = prev;
}

void main() {
  group('Router feature flags (routerProvider real)', () {
    // Test 1 — /documents/:id con documents=false → redirige (no llega al doc)
    testWidgets('Acceso a /documents/:id con documents=false redirige a /', (
      tester,
    ) async {
      late GoRouter router;
      addTearDown(_suppressBuildErrors());

      await tester.pumpWidget(
        ProviderScope(
          overrides: [
            sessionProvider.overrideWith(
              (ref) => FakeSessionController(ref, testSession),
            ),
            platformFeaturesProvider.overrideWith(
              (_) async =>
                  const PlatformFeatures(documents: false, invoicing: false),
            ),
          ],
          child: Consumer(
            builder: (context, ref, _) {
              router = ref.watch(routerProvider);
              return MaterialApp.router(routerConfig: router);
            },
          ),
        ),
      );
      await tester.pumpAndSettle();

      router.go('/documents/doc-abc');
      await tester.pump();

      expect(
        router.routerDelegate.currentConfiguration.uri.path,
        isNot('/documents/doc-abc'),
      );
    });

    // Test 2 — /documents/:id con documents=true → no redirige
    testWidgets('Acceso a /documents/:id con documents=true no redirige', (
      tester,
    ) async {
      late GoRouter router;
      addTearDown(_suppressBuildErrors());

      await tester.pumpWidget(
        ProviderScope(
          overrides: [
            sessionProvider.overrideWith(
              (ref) => FakeSessionController(ref, testSession),
            ),
            platformFeaturesProvider.overrideWith(
              (_) async =>
                  const PlatformFeatures(documents: true, invoicing: false),
            ),
            documentDetailProvider('doc-abc').overrideWith(
              (_) async => const ClientDocument(
                id: 'doc-abc',
                documentType: 'factura',
                displayName: 'Factura de prueba',
                fileName: 'factura.pdf',
                status: 'published',
              ),
            ),
            documentReadProvider('doc-abc').overrideWith((_) async {}),
          ],
          child: Consumer(
            builder: (context, ref, _) {
              router = ref.watch(routerProvider);
              return MaterialApp.router(routerConfig: router);
            },
          ),
        ),
      );
      await tester.pumpAndSettle();

      router.go('/documents/doc-abc');
      await tester.pump();

      expect(
        router.routerDelegate.currentConfiguration.uri.path,
        equals('/documents/doc-abc'),
      );
    });

    // Test 3 — /invoicing con invoicing=false → redirige a /
    testWidgets('Acceso a /invoicing con invoicing=false redirige a /', (
      tester,
    ) async {
      late GoRouter router;
      addTearDown(_suppressBuildErrors());

      await tester.pumpWidget(
        ProviderScope(
          overrides: [
            sessionProvider.overrideWith(
              (ref) => FakeSessionController(ref, testSession),
            ),
            platformFeaturesProvider.overrideWith(
              (_) async =>
                  const PlatformFeatures(documents: false, invoicing: false),
            ),
          ],
          child: Consumer(
            builder: (context, ref, _) {
              router = ref.watch(routerProvider);
              return MaterialApp.router(routerConfig: router);
            },
          ),
        ),
      );
      await tester.pumpAndSettle();

      router.go('/invoicing');
      await tester.pump();

      expect(router.routerDelegate.currentConfiguration.uri.path, equals('/'));
    });

    // Test 4 — /invoicing/drafts/new con invoicing=false → redirige a /
    testWidgets(
      'Acceso a /invoicing/drafts/new con invoicing=false redirige a /',
      (tester) async {
        late GoRouter router;
        addTearDown(_suppressBuildErrors());

        await tester.pumpWidget(
          ProviderScope(
            overrides: [
              sessionProvider.overrideWith(
                (ref) => FakeSessionController(ref, testSession),
              ),
              platformFeaturesProvider.overrideWith(
                (_) async =>
                    const PlatformFeatures(documents: false, invoicing: false),
              ),
            ],
            child: Consumer(
              builder: (context, ref, _) {
                router = ref.watch(routerProvider);
                return MaterialApp.router(routerConfig: router);
              },
            ),
          ),
        );
        await tester.pumpAndSettle();

        router.go('/invoicing/drafts/new');
        await tester.pump();

        expect(
          router.routerDelegate.currentConfiguration.uri.path,
          equals('/'),
        );
      },
    );

    // Test 5 — /invoicing/customers con invoicing=false → redirige a /
    testWidgets(
      'Acceso a /invoicing/customers con invoicing=false redirige a /',
      (tester) async {
        late GoRouter router;
        addTearDown(_suppressBuildErrors());

        await tester.pumpWidget(
          ProviderScope(
            overrides: [
              sessionProvider.overrideWith(
                (ref) => FakeSessionController(ref, testSession),
              ),
              platformFeaturesProvider.overrideWith(
                (_) async =>
                    const PlatformFeatures(documents: false, invoicing: false),
              ),
            ],
            child: Consumer(
              builder: (context, ref, _) {
                router = ref.watch(routerProvider);
                return MaterialApp.router(routerConfig: router);
              },
            ),
          ),
        );
        await tester.pumpAndSettle();

        router.go('/invoicing/customers');
        await tester.pump();

        expect(
          router.routerDelegate.currentConfiguration.uri.path,
          equals('/'),
        );
      },
    );

    // Test 6 — AsyncLoading → muestra splash (CircularProgressIndicator)
    testWidgets('Estado cargando muestra splash y no el contenido solicitado', (
      tester,
    ) async {
      // _SplashScreen = CircularProgressIndicator; no requiere providers de red.
      late GoRouter router;
      final completer = Completer<PlatformFeatures>();

      await tester.pumpWidget(
        ProviderScope(
          overrides: [
            sessionProvider.overrideWith(
              (ref) => FakeSessionController(ref, testSession),
            ),
            platformFeaturesProvider.overrideWith((_) => completer.future),
          ],
          child: Consumer(
            builder: (context, ref, _) {
              router = ref.watch(routerProvider);
              return MaterialApp.router(routerConfig: router);
            },
          ),
        ),
      );
      await tester.pump(); // no pumpAndSettle — el Future no resuelve

      router.go('/documents/doc-xyz');
      await tester.pump();

      // El router debe estar en /splash con ?next= mientras carga.
      final uri = router.routerDelegate.currentConfiguration.uri;
      expect(uri.path, equals('/splash'));
      expect(uri.queryParameters['next'], isNotNull);
      expect(find.byType(CircularProgressIndicator), findsOneWidget);
      completer.complete(const PlatformFeatures());
      await tester.pumpAndSettle();
    });

    // Test 7 — feature activado permite acceso a /invoicing
    testWidgets('Feature invoicing activado permite acceder a /invoicing', (
      tester,
    ) async {
      late GoRouter router;
      addTearDown(_suppressBuildErrors());

      await tester.pumpWidget(
        ProviderScope(
          overrides: [
            sessionProvider.overrideWith(
              (ref) => FakeSessionController(ref, testSession),
            ),
            platformFeaturesProvider.overrideWith(
              (_) async =>
                  const PlatformFeatures(documents: true, invoicing: true),
            ),
          ],
          child: Consumer(
            builder: (context, ref, _) {
              router = ref.watch(routerProvider);
              return MaterialApp.router(routerConfig: router);
            },
          ),
        ),
      );
      await tester.pumpAndSettle();

      router.go('/invoicing');
      await tester.pump();

      expect(
        router.routerDelegate.currentConfiguration.uri.path,
        equals('/invoicing'),
      );
    });

    // Test 8 — ?next= preserva la ruta destino al resolver el splash
    testWidgets(
      'Ruta con ?next= se resuelve al terminar la carga de features',
      (tester) async {
        late GoRouter router;
        final completer = Completer<PlatformFeatures>();
        addTearDown(_suppressBuildErrors());

        await tester.pumpWidget(
          ProviderScope(
            overrides: [
              sessionProvider.overrideWith(
                (ref) => FakeSessionController(ref, testSession),
              ),
              platformFeaturesProvider.overrideWith((_) => completer.future),
            ],
            child: Consumer(
              builder: (context, ref, _) {
                router = ref.watch(routerProvider);
                return MaterialApp.router(routerConfig: router);
              },
            ),
          ),
        );
        await tester.pump();

        // Navegar mientras features aun carga.
        router.go('/invoicing');
        await tester.pump();

        // Debe estar en /splash con ?next= preservado.
        final splashUri = router.routerDelegate.currentConfiguration.uri;
        expect(splashUri.path, equals('/splash'));
        expect(splashUri.queryParameters['next'], isNotNull);

        // Resolver features con invoicing habilitado.
        completer.complete(
          const PlatformFeatures(documents: false, invoicing: true),
        );
        await tester.pumpAndSettle();

        // Ahora debe resolver a /invoicing.
        expect(
          router.routerDelegate.currentConfiguration.uri.path,
          equals('/invoicing'),
        );
      },
    );
  });
}
