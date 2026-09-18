import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:gestinem/features/documents/presentation/documentation_screen.dart';
import 'package:gestinem/features/platform/features_provider.dart';
import 'package:go_router/go_router.dart';

void main() {
  for (final enlaceDirecto in [false, true]) {
    testWidgets('vuelve al inicio con enlace directo=$enlaceDirecto', (
      tester,
    ) async {
      final router = GoRouter(
        initialLocation: enlaceDirecto ? '/documentation' : '/',
        routes: [
          GoRoute(
            path: '/',
            builder: (_, _) => const Scaffold(body: Text('Inicio')),
          ),
          GoRoute(
            path: '/documentation',
            builder: (_, _) => const DocumentationScreen(),
          ),
        ],
      );
      addTearDown(router.dispose);
      await tester.pumpWidget(
        ProviderScope(
          overrides: [
            platformFeaturesProvider.overrideWith(
              (_) async => const PlatformFeatures(),
            ),
          ],
          child: MaterialApp.router(routerConfig: router),
        ),
      );
      await tester.pumpAndSettle();
      if (!enlaceDirecto) {
        unawaited(router.push('/documentation'));
        await tester.pumpAndSettle();
      }
      expect(router.canPop(), !enlaceDirecto);
      await tester.tap(find.byKey(const Key('documentation-back')));
      await tester.pumpAndSettle();
      expect(find.text('Inicio'), findsOneWidget);
      expect(router.canPop(), isFalse);
    });
  }

  for (final documentos in [false, true]) {
    for (final certificados in [false, true]) {
      testWidgets(
        'menu respeta documentos=$documentos certificados=$certificados',
        (tester) async {
          final router = GoRouter(
            initialLocation: '/documentation',
            routes: [
              GoRoute(
                path: '/documentation',
                builder: (_, _) => const DocumentationScreen(),
              ),
              GoRoute(
                path: '/documents',
                builder: (_, _) => const Scaffold(body: Text('Documentos')),
              ),
              GoRoute(
                path: '/certificates',
                builder: (_, _) => const Scaffold(body: Text('Certificados')),
              ),
            ],
          );
          addTearDown(router.dispose);
          await tester.pumpWidget(
            ProviderScope(
              overrides: [
                platformFeaturesProvider.overrideWith(
                  (_) async => PlatformFeatures(
                    documents: documentos,
                    certificates: certificados,
                  ),
                ),
              ],
              child: MaterialApp.router(routerConfig: router),
            ),
          );
          await tester.pumpAndSettle();
          expect(find.text('Documentaci\u00f3n'), findsOneWidget);
          final documentosTile = find.byKey(
            const Key('documentation-documents'),
          );
          final certificadosTile = find.byKey(
            const Key('documentation-certificates'),
          );
          expect(
            tester.widget<ListTile>(documentosTile).onTap != null,
            documentos,
          );
          expect(
            tester.widget<ListTile>(certificadosTile).onTap != null,
            certificados,
          );
          await tester.tap(certificadosTile);
          await tester.pumpAndSettle();
          expect(
            find.text('Certificados'),
            certificados ? findsOneWidget : findsNothing,
          );
          expect(router.canPop(), certificados);
          if (certificados) router.pop();
          await tester.pumpAndSettle();
          await tester.tap(documentosTile);
          await tester.pumpAndSettle();
          expect(
            find.text('Documentos'),
            documentos ? findsOneWidget : findsNothing,
          );
          expect(router.canPop(), documentos);
        },
      );
    }
  }

  testWidgets('carga disponibilidad y permite reintentar tras error', (
    tester,
  ) async {
    final carga = Completer<PlatformFeatures>();
    var intentos = 0;
    await tester.pumpWidget(
      ProviderScope(
        overrides: [
          platformFeaturesProvider.overrideWith((_) {
            intentos++;
            return intentos == 1
                ? carga.future
                : Future.value(const PlatformFeatures(certificates: true));
          }),
        ],
        child: const MaterialApp(home: DocumentationScreen()),
      ),
    );
    expect(find.byType(CircularProgressIndicator), findsOneWidget);
    expect(find.byKey(const Key('documentation-certificates')), findsNothing);
    carga.completeError(Exception('Sin conexion'));
    await tester.pumpAndSettle();
    expect(
      find.text('No se pudo consultar la disponibilidad.'),
      findsOneWidget,
    );
    await tester.tap(find.text('Reintentar'));
    await tester.pumpAndSettle();
    expect(intentos, 2);
    expect(
      tester
          .widget<ListTile>(find.byKey(const Key('documentation-certificates')))
          .onTap,
      isNotNull,
    );
  });
}
