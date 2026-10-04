import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:url_launcher/url_launcher.dart';

import '../../../core/api/api_client.dart';
import '../domain/subvencion.dart';
import 'subvenciones_providers.dart';

class SubvencionDetailScreen extends ConsumerWidget {
  const SubvencionDetailScreen({super.key, required this.codigo});
  final String codigo;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final detail = ref.watch(subvencionProvider(codigo));
    return Scaffold(
      appBar: AppBar(title: const Text('Detalle de la ayuda')),
      body: detail.when(
        loading: () => const Center(child: CircularProgressIndicator()),
        error: (error, _) => Center(
          child: Padding(
            padding: const EdgeInsets.all(24),
            child: Text(apiErrorMessage(error), textAlign: TextAlign.center),
          ),
        ),
        data: (item) => ListView(
          padding: const EdgeInsets.all(16),
          children: [
            Text(
              item.titulo,
              style: Theme.of(
                context,
              ).textTheme.headlineSmall?.copyWith(fontWeight: FontWeight.w700),
            ),
            const SizedBox(height: 12),
            _FichaDatos(item: item),
            if (item.resumen != null) ...[
              const SizedBox(height: 20),
              Text(
                'Resumen orientativo',
                style: Theme.of(context).textTheme.titleLarge,
              ),
              const SizedBox(height: 8),
              _Resumen(resumen: item.resumen!),
            ] else if (item.resumenCorto?.isNotEmpty == true) ...[
              const SizedBox(height: 20),
              Text('Resumen', style: Theme.of(context).textTheme.titleLarge),
              const SizedBox(height: 8),
              Text(item.resumenCorto!),
            ],
            if (item.finalidad?.isNotEmpty == true) ...[
              const SizedBox(height: 20),
              Text(
                'Finalidad oficial',
                style: Theme.of(context).textTheme.titleLarge,
              ),
              const SizedBox(height: 8),
              Text(item.finalidad!),
            ],
            if (item.beneficiariosOficiales.isNotEmpty) ...[
              const SizedBox(height: 20),
              Text(
                'Beneficiarios',
                style: Theme.of(context).textTheme.titleLarge,
              ),
              const SizedBox(height: 8),
              ...item.beneficiariosOficiales.map(
                (e) => ListTile(
                  contentPadding: EdgeInsets.zero,
                  dense: true,
                  leading: const Icon(Icons.check_circle_outline),
                  title: Text(e),
                ),
              ),
            ],
            if (item.enlaces.isNotEmpty) ...[
              const SizedBox(height: 20),
              Text(
                'Fuentes oficiales',
                style: Theme.of(context).textTheme.titleLarge,
              ),
              const SizedBox(height: 8),
              ...item.enlaces.map(
                (e) => Card(
                  child: ListTile(
                    title: Text(e.titulo),
                    trailing: const Icon(Icons.open_in_new),
                    onTap: () => _abrir(context, e),
                  ),
                ),
              ),
            ],
            if (item.avisoLegal?.isNotEmpty == true) ...[
              const SizedBox(height: 20),
              Container(
                padding: const EdgeInsets.all(12),
                decoration: BoxDecoration(
                  color: Theme.of(context).colorScheme.surfaceContainerHighest,
                  borderRadius: BorderRadius.circular(12),
                ),
                child: Text(
                  item.avisoLegal!,
                  style: Theme.of(context).textTheme.bodySmall,
                ),
              ),
            ],
            const SizedBox(height: 24),
          ],
        ),
      ),
    );
  }

  Future<void> _abrir(BuildContext context, EnlaceSubvencion enlace) async {
    final uri = Uri.tryParse(enlace.url);
    final ok =
        uri != null &&
        {'http', 'https'}.contains(uri.scheme) &&
        await launchUrl(uri, mode: LaunchMode.externalApplication);
    if (!ok && context.mounted) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('No se pudo abrir el enlace oficial.')),
      );
    }
  }
}

class _FichaDatos extends StatelessWidget {
  const _FichaDatos({required this.item});
  final Subvencion item;

  @override
  Widget build(BuildContext context) {
    final rows = <(IconData, String, String)>[
      (Icons.account_balance_outlined, 'Organismo', item.organo),
      (Icons.public, 'Ámbito', item.ambito),
      if (item.fechaFin != null)
        (Icons.event, 'Fin de plazo', _fecha(item.fechaFin!)),
      if (item.plazoTexto?.isNotEmpty == true)
        (Icons.event_note, 'Plazo', item.plazoTexto!),
      if (item.presupuesto != null)
        (Icons.euro, 'Presupuesto', _euros(item.presupuesto!)),
      (Icons.tag, 'Código BDNS', item.codigo),
    ].where((row) => row.$3.isNotEmpty).toList();
    return Card(
      child: Padding(
        padding: const EdgeInsets.symmetric(vertical: 6),
        child: Column(
          children: rows
              .map(
                (row) => ListTile(
                  dense: true,
                  leading: Icon(row.$1),
                  title: Text(row.$2),
                  subtitle: Text(row.$3),
                ),
              )
              .toList(),
        ),
      ),
    );
  }
}

class _Resumen extends StatelessWidget {
  const _Resumen({required this.resumen});
  final Map<String, dynamic> resumen;

  @override
  Widget build(BuildContext context) {
    const labels = {
      'resumen': 'En qué consiste',
      'beneficiarios': 'A quién se dirige',
      'que_financia': 'Qué financia',
      'cuantia': 'Cuantía',
      'plazo': 'Plazo',
    };
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        for (final entry in labels.entries)
          if ((resumen[entry.key]?.toString() ?? '').isNotEmpty)
            Padding(
              padding: const EdgeInsets.only(bottom: 12),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    entry.value,
                    style: const TextStyle(fontWeight: FontWeight.w700),
                  ),
                  const SizedBox(height: 3),
                  Text(resumen[entry.key].toString()),
                ],
              ),
            ),
        if (resumen['requisitos'] is List &&
            (resumen['requisitos'] as List).isNotEmpty) ...[
          const Text(
            'Requisitos principales',
            style: TextStyle(fontWeight: FontWeight.w700),
          ),
          ...(resumen['requisitos'] as List).map(
            (e) => ListTile(
              dense: true,
              contentPadding: EdgeInsets.zero,
              leading: const Icon(Icons.arrow_right),
              title: Text(e.toString()),
            ),
          ),
        ],
      ],
    );
  }
}

String _fecha(DateTime value) =>
    '${value.day.toString().padLeft(2, '0')}/${value.month.toString().padLeft(2, '0')}/${value.year}';

String _euros(double value) {
  final whole = value.round().toString();
  final buffer = StringBuffer();
  for (var index = 0; index < whole.length; index++) {
    if (index > 0 && (whole.length - index) % 3 == 0) buffer.write('.');
    buffer.write(whole[index]);
  }
  return '${buffer.toString()} €';
}
