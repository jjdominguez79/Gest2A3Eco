import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:gestinem/features/dgt/domain/dgt_expediente.dart';
import 'package:gestinem/features/dgt/presentation/dgt_providers.dart';
import 'package:gestinem/features/dgt/presentation/dgt_screen.dart';

void main() {
  test('normaliza telefonos espanoles para WhatsApp', () {
    expect(normalizarTelefonoWhatsAppDgt('600 000 001'), '34600000001');
    expect(normalizarTelefonoWhatsAppDgt('+34 600 000 001'), '34600000001');
    expect(normalizarTelefonoWhatsAppDgt('0034 600 000 001'), '34600000001');
  });

  test('interpreta expediente, partes y comprobacion DGT', () {
    final expediente = DgtExpediente.fromJson({
      'id': 'exp-1',
      'referencia': 'DGT-2026-0001',
      'titulo': 'Cambio de titularidad',
      'estado': 'pendiente_revision',
      'partes': {
        'vendedor': {
          'estado': 'completado',
          'nombre': 'Ana',
          'telefono': '600000001',
        },
        'comprador': {
          'estado': 'en_curso',
          'nombre': 'Luis',
          'telefono': '600000002',
        },
      },
      'vehiculo': {'matricula': '1234ABC'},
    });
    final check = DgtComprobacion.fromJson({
      'completo': false,
      'errores': ['Comprador: falta el domicilio.'],
      'partes': {
        'vendedor': {'completo': true},
        'comprador': {'completo': false},
      },
    });

    expect(expediente.referencia, 'DGT-2026-0001');
    expect(expediente.partes['vendedor']!.estado, 'completado');
    expect(expediente.matricula, '1234ABC');
    expect(check.completo, isFalse);
    expect(check.partesCompletas['vendedor'], isTrue);
  });

  testWidgets('muestra expedientes y valida los telefonos al crear', (
    tester,
  ) async {
    const expediente = DgtExpediente(
      id: 'exp-1',
      referencia: 'DGT-2026-0001',
      titulo: 'Cambio de titularidad',
      estado: 'enlaces_enviados',
      matricula: '1234ABC',
      partes: {
        'vendedor': DgtParteResumen(
          rol: 'vendedor',
          estado: 'completado',
          nombre: 'Ana',
          telefono: '600000001',
        ),
        'comprador': DgtParteResumen(
          rol: 'comprador',
          estado: 'pendiente',
          nombre: 'Luis',
          telefono: '600000002',
        ),
      },
    );
    await tester.pumpWidget(
      ProviderScope(
        overrides: [
          expedientesDgtProvider.overrideWith((ref) async => [expediente]),
        ],
        child: const MaterialApp(home: DgtScreen()),
      ),
    );
    await tester.pumpAndSettle();

    expect(find.text('DGT-2026-0001'), findsOneWidget);
    expect(find.text('Vendedor: completado'), findsOneWidget);
    expect(find.byKey(const Key('dgt-comprobar-exp-1')), findsOneWidget);

    await tester.tap(find.byKey(const Key('dgt-nuevo')));
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const Key('dgt-crear-confirmar')));
    await tester.pump();

    expect(
      find.text('Indica un teléfono válido para enviar el enlace.'),
      findsNWidgets(2),
    );
  });
}
