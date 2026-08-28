import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:go_router/go_router.dart';
import 'package:gestinem/features/auth/domain/user_profile.dart';
import 'package:gestinem/features/platform/features_provider.dart';

import 'test_helpers.dart';

// ---------------------------------------------------------------------------
// Helper: construye un GoRouter con la misma logica de redirect que routerProvider
// usando valores inyectados, de modo que se pueda testear sin Riverpod completo.
// ---------------------------------------------------------------------------

GoRouter _buildRouter({
  required AsyncValue<AuthSession?> session,
  required AsyncValue<PlatformFeatures> featuresAsync,
  String initialLocation = '/',
}) {
  return GoRouter(
    initialLocation: initialLocation,
    redirect: (context, state) {
      final loggedIn = session.valueOrNull != null;

      if (session.isLoading) {
        return {'/splash', '/auth/callback'}.contains(state.matchedLocation)
            ? null
            : '/splash';
      }
      if (!loggedIn) {
        if (state.matchedLocation == '/login' ||
            state.matchedLocation == '/accept-invite' ||
            state.matchedLocation == '/forgot-password' ||
            state.matchedLocation.startsWith('/reset-password')) {
          return null;
        }
        return '/login';
      }
      if (state.matchedLocation == '/login' ||
          state.matchedLocation == '/splash') {
        return '/';
      }

      // Proteger rutas de documentos e invoicing
      if (state.matchedLocation.startsWith('/documents') ||
          state.matchedLocation.startsWith('/invoicing')) {
        if (featuresAsync.isLoading) return '/splash';
        if (featuresAsync.hasError) return '/';

        final features = featuresAsync.value!;
        if (state.matchedLocation.startsWith('/documents') &&
            !features.documents) {
          return '/';
        }
        if (state.matchedLocation.startsWith('/invoicing') &&
            !features.invoicing) {
          return '/';
        }
      }
      return null;
    },
    routes: [
      GoRoute(
        path: '/splash',
        builder: (_, _) =>
            const Scaffold(body: Center(child: CircularProgressIndicator())),
      ),
      GoRoute(
        path: '/login',
        builder: (_, _) => const Scaffold(body: Text('Login')),
      ),
      GoRoute(
        path: '/',
        builder: (_, _) => const Scaffold(body: Text('Home')),
      ),
      GoRoute(
        path: '/documents/:id',
        builder: (_, st) =>
            Scaffold(body: Text('Document ${st.pathParameters['id']}')),
      ),
      GoRoute(
        path: '/documents',
        builder: (_, _) => const Scaffold(body: Text('Documents')),
      ),
      GoRoute(
        path: '/invoicing',
        builder: (_, _) => const Scaffold(body: Text('Invoicing')),
      ),
      GoRoute(
        path: '/invoicing/drafts/new',
        builder: (_, _) => const Scaffold(body: Text('New Draft')),
      ),
      GoRoute(
        path: '/invoicing/customers',
        builder: (_, _) => const Scaffold(body: Text('Customers')),
      ),
    ],
  );
}

Widget _wrap(GoRouter router) => MaterialApp.router(routerConfig: router);

void main() {
  group('Router feature flags', () {
    // Test 1
    testWidgets(
        'Acceso a /documents/:id con documents=false redirige a /',
        (tester) async {
      final router = _buildRouter(
        session: const AsyncData(testSession),
        featuresAsync: const AsyncData(
          PlatformFeatures(documents: false, invoicing: false),
        ),
        initialLocation: '/documents/doc-abc',
      );
      await tester.pumpWidget(_wrap(router));
      await tester.pumpAndSettle();

      expect(find.text('Home'), findsOneWidget);
      expect(find.text('Document doc-abc'), findsNothing);
    });

    // Test 2
    testWidgets(
        'Acceso a /documents/:id con documents=true llega al documento',
        (tester) async {
      final router = _buildRouter(
        session: const AsyncData(testSession),
        featuresAsync: const AsyncData(
          PlatformFeatures(documents: true, invoicing: false),
        ),
        initialLocation: '/documents/doc-abc',
      );
      await tester.pumpWidget(_wrap(router));
      await tester.pumpAndSettle();

      expect(find.text('Document doc-abc'), findsOneWidget);
      expect(find.text('Home'), findsNothing);
    });

    // Test 3
    testWidgets(
        'Acceso a /invoicing con invoicing=false redirige a /',
        (tester) async {
      final router = _buildRouter(
        session: const AsyncData(testSession),
        featuresAsync: const AsyncData(
          PlatformFeatures(documents: false, invoicing: false),
        ),
        initialLocation: '/invoicing',
      );
      await tester.pumpWidget(_wrap(router));
      await tester.pumpAndSettle();

      expect(find.text('Home'), findsOneWidget);
      expect(find.text('Invoicing'), findsNothing);
    });

    // Test 4
    testWidgets(
        'Acceso a /invoicing/drafts/new con invoicing=false redirige a /',
        (tester) async {
      final router = _buildRouter(
        session: const AsyncData(testSession),
        featuresAsync: const AsyncData(
          PlatformFeatures(documents: false, invoicing: false),
        ),
        initialLocation: '/invoicing/drafts/new',
      );
      await tester.pumpWidget(_wrap(router));
      await tester.pumpAndSettle();

      expect(find.text('Home'), findsOneWidget);
      expect(find.text('New Draft'), findsNothing);
    });

    // Test 5
    testWidgets(
        'Acceso a /invoicing/customers con invoicing=false redirige a /',
        (tester) async {
      final router = _buildRouter(
        session: const AsyncData(testSession),
        featuresAsync: const AsyncData(
          PlatformFeatures(documents: false, invoicing: false),
        ),
        initialLocation: '/invoicing/customers',
      );
      await tester.pumpWidget(_wrap(router));
      await tester.pumpAndSettle();

      expect(find.text('Home'), findsOneWidget);
      expect(find.text('Customers'), findsNothing);
    });

    // Test 6
    testWidgets(
        'Estado AsyncLoading muestra splash en lugar de pantalla de destino',
        (tester) async {
      final router = _buildRouter(
        session: const AsyncData(testSession),
        featuresAsync: const AsyncLoading(),
        initialLocation: '/documents/doc-xyz',
      );
      await tester.pumpWidget(_wrap(router));
      await tester.pump(); // no pumpAndSettle para mantener el estado loading

      // Debe estar en /splash (CircularProgressIndicator) o redirigido
      expect(find.text('Document doc-xyz'), findsNothing);
    });

    // Test 7
    testWidgets(
        'Feature activado despues de cargar permite acceso',
        (tester) async {
      final router = _buildRouter(
        session: const AsyncData(testSession),
        featuresAsync: const AsyncData(
          PlatformFeatures(documents: true, invoicing: true),
        ),
        initialLocation: '/invoicing',
      );
      await tester.pumpWidget(_wrap(router));
      await tester.pumpAndSettle();

      expect(find.text('Invoicing'), findsOneWidget);
    });
  });
}
