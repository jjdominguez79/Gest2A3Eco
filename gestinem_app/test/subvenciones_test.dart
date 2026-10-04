import 'package:flutter_test/flutter_test.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:gestinem/core/notifications/notifications_service.dart';
import 'package:gestinem/features/platform/features_provider.dart';
import 'package:gestinem/features/subvenciones/domain/subvencion.dart';
import 'package:gestinem/features/subvenciones/presentation/subvenciones_providers.dart';
import 'package:gestinem/features/subvenciones/presentation/subvenciones_screen.dart';

void main() {
  test('interpreta una convocatoria del backend', () {
    final item = Subvencion.fromJson({
      'codigo_bdns': '123456',
      'titulo': 'Ayuda para pymes',
      'organo': 'Ministerio',
      'ambito': 'ESTATAL',
      'alcance_nacional': true,
      'ccaa': <String>[],
      'provincias': <String>[],
      'fecha_fin': '2026-12-31',
      'presupuesto': 250000,
      'etiquetas': ['digitalizacion'],
      'beneficiarios_oficiales': ['Pymes'],
      'sectores': <String>[],
      'instrumentos': <String>[],
      'enlaces': [
        {'titulo': 'Ficha oficial', 'url': 'https://example.test'},
      ],
    });

    expect(item.codigo, '123456');
    expect(item.alcanceNacional, isTrue);
    expect(item.fechaFin, DateTime(2026, 12, 31));
    expect(item.presupuesto, 250000);
    expect(item.enlaces.single.titulo, 'Ficha oficial');
  });

  test('interpreta preferencias territoriales', () {
    final preferences = PreferenciasSubvenciones.fromJson({
      'notificaciones_activas': true,
      'incluir_nacionales': false,
      'usar_territorio_empresa': true,
      'territorio_empresa': {'municipio': 'Madrid'},
      'suscripciones': [
        {'nivel': 'AUTONOMICA', 'codigo': 'ES52', 'nombre': 'Valencia'},
      ],
    });

    expect(preferences.notificacionesActivas, isTrue);
    expect(preferences.suscripciones.single.clave, 'AUTONOMICA:ES52');
  });

  test('expone la funcion y el destino de notificacion de subvenciones', () {
    final features = PlatformFeatures.fromJson({'subsidies': true});
    expect(features.subsidies, isTrue);
    expect(
      notificationTargetType({
        'target_type': 'subvencion',
        'target_id': '123456',
      }),
      'subvencion',
    );
    expect(
      notificationTargetId({
        'target_type': 'subvencion',
        'target_id': '123456',
      }),
      '123456',
    );
  });

  testWidgets('muestra el catalogo para el cliente', (tester) async {
    const item = Subvencion(
      codigo: '123456',
      titulo: 'Ayuda para digitalizar pymes',
      organo: 'Ministerio de Industria',
      ambito: 'ESTATAL',
      alcanceNacional: true,
      ccaa: [],
      provincias: [],
      etiquetas: ['digitalizacion'],
      enlaces: [],
      beneficiariosOficiales: [],
      sectores: [],
      instrumentos: [],
      resumenCorto: 'Financia proyectos de modernizacion.',
    );
    await tester.pumpWidget(
      ProviderScope(
        overrides: [
          subvencionesProvider.overrideWith(
            (ref) async => const ListaSubvenciones(total: 1, elementos: [item]),
          ),
        ],
        child: const MaterialApp(home: SubvencionesScreen()),
      ),
    );
    await tester.pumpAndSettle();

    expect(find.text('Ayudas y subvenciones'), findsOneWidget);
    expect(find.text('Ayuda para digitalizar pymes'), findsOneWidget);
    expect(find.text('1 convocatorias vigentes'), findsOneWidget);
    expect(find.byKey(const Key('subvenciones-preferencias')), findsOneWidget);
  });
}
