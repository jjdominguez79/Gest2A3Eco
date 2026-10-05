import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../../core/api/api_client.dart';
import '../domain/subvencion.dart';
import 'subvenciones_admin_providers.dart';

class SubvencionesAdminScreen extends ConsumerStatefulWidget {
  const SubvencionesAdminScreen({super.key});

  @override
  ConsumerState<SubvencionesAdminScreen> createState() =>
      _SubvencionesAdminScreenState();
}

class _SubvencionesAdminScreenState
    extends ConsumerState<SubvencionesAdminScreen> {
  final _consulta = TextEditingController();
  Timer? _debounce;
  bool _sincronizando = false;

  @override
  void dispose() {
    _debounce?.cancel();
    _consulta.dispose();
    super.dispose();
  }

  void _actualizarFiltros(FiltrosSubvencionesAdmin value) {
    ref.read(filtrosSubvencionesAdminProvider.notifier).state = value;
  }

  void _buscar(String value) {
    _debounce?.cancel();
    _debounce = Timer(const Duration(milliseconds: 350), () {
      if (!mounted) return;
      final current = ref.read(filtrosSubvencionesAdminProvider);
      _actualizarFiltros(current.copyWith(consulta: value, pagina: 0));
    });
  }

  Future<void> _sincronizar() async {
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (dialogContext) => AlertDialog(
        title: const Text('Actualizar base de datos'),
        content: const Text(
          'Se consultarán BDNS y los boletines oficiales. El proceso continuará '
          'en el servidor aunque cierres esta pantalla.',
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(dialogContext, false),
            child: const Text('Cancelar'),
          ),
          FilledButton(
            onPressed: () => Navigator.pop(dialogContext, true),
            child: const Text('Actualizar'),
          ),
        ],
      ),
    );
    if (confirmed != true || !mounted) return;
    setState(() => _sincronizando = true);
    try {
      await ref.read(subvencionesAdminRepositoryProvider).sincronizar();
      ref.invalidate(dashboardSubvencionesAdminProvider);
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(content: Text('Sincronización iniciada.')),
        );
      }
    } catch (error) {
      if (mounted) {
        ScaffoldMessenger.of(
          context,
        ).showSnackBar(SnackBar(content: Text(apiErrorMessage(error))));
      }
    } finally {
      if (mounted) setState(() => _sincronizando = false);
    }
  }

  Future<void> _editar(Subvencion item, {bool? visible, bool? revisada}) async {
    try {
      await ref
          .read(subvencionesAdminRepositoryProvider)
          .editar(item.codigo, visible: visible, revisada: revisada);
      ref.invalidate(listaSubvencionesAdminProvider);
      ref.invalidate(dashboardSubvencionesAdminProvider);
      ref.invalidate(subvencionAdminProvider(item.codigo));
    } catch (error) {
      if (mounted) {
        ScaffoldMessenger.of(
          context,
        ).showSnackBar(SnackBar(content: Text(apiErrorMessage(error))));
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    final filters = ref.watch(filtrosSubvencionesAdminProvider);
    final dashboard = ref.watch(dashboardSubvencionesAdminProvider);
    final listing = ref.watch(listaSubvencionesAdminProvider);
    final sources = <String>{
      '',
      filters.fuente,
      ...?dashboard.valueOrNull?.fuentes.keys,
    }.toList()..sort();

    return Scaffold(
      appBar: AppBar(
        title: const Text('Base de datos de ayudas'),
        actions: [
          IconButton(
            key: const Key('admin-subvenciones-refrescar'),
            tooltip: 'Refrescar pantalla',
            onPressed: () {
              ref.invalidate(dashboardSubvencionesAdminProvider);
              ref.invalidate(listaSubvencionesAdminProvider);
            },
            icon: const Icon(Icons.refresh),
          ),
          IconButton(
            key: const Key('admin-subvenciones-sincronizar'),
            tooltip: 'Actualizar desde fuentes oficiales',
            onPressed: _sincronizando ? null : _sincronizar,
            icon: _sincronizando
                ? const SizedBox.square(
                    dimension: 20,
                    child: CircularProgressIndicator(strokeWidth: 2),
                  )
                : const Icon(Icons.cloud_sync_outlined),
          ),
        ],
      ),
      body: Column(
        children: [
          dashboard.when(
            loading: () => const LinearProgressIndicator(),
            error: (error, _) => _AvisoError(
              mensaje: apiErrorMessage(error),
              onRetry: () => ref.invalidate(dashboardSubvencionesAdminProvider),
            ),
            data: (data) => _ResumenDashboard(data: data),
          ),
          _Filtros(
            consulta: _consulta,
            filters: filters,
            sources: sources,
            onSearch: _buscar,
            onChange: _actualizarFiltros,
          ),
          Expanded(
            child: listing.when(
              loading: () => const Center(child: CircularProgressIndicator()),
              error: (error, _) => _AvisoError(
                mensaje: apiErrorMessage(error),
                onRetry: () => ref.invalidate(listaSubvencionesAdminProvider),
              ),
              data: (data) => _Listado(
                data: data,
                filters: filters,
                onChangePage: (page) =>
                    _actualizarFiltros(filters.copyWith(pagina: page)),
                onEdit: _editar,
              ),
            ),
          ),
        ],
      ),
    );
  }
}

class _ResumenDashboard extends StatelessWidget {
  const _ResumenDashboard({required this.data});
  final DashboardSubvencionesAdmin data;

  @override
  Widget build(BuildContext context) => SingleChildScrollView(
    scrollDirection: Axis.horizontal,
    padding: const EdgeInsets.fromLTRB(12, 12, 12, 4),
    child: Row(
      children: [
        _Metrica(
          label: 'Total',
          value: data.convocatorias,
          icon: Icons.storage,
        ),
        _Metrica(
          label: 'Vigentes',
          value: data.vigentes,
          icon: Icons.event_available,
        ),
        _Metrica(
          label: 'Ocultas',
          value: data.ocultas,
          icon: Icons.visibility_off_outlined,
        ),
        _Metrica(
          label: 'Revisadas',
          value: data.revisadas,
          icon: Icons.fact_check_outlined,
        ),
        _Metrica(
          label: 'Suscriptores',
          value: data.suscriptores,
          icon: Icons.notifications_active_outlined,
        ),
        _Metrica(
          label: 'Fallos',
          value: data.fallosEntrega,
          icon: Icons.warning_amber_outlined,
        ),
      ],
    ),
  );
}

class _Metrica extends StatelessWidget {
  const _Metrica({
    required this.label,
    required this.value,
    required this.icon,
  });
  final String label;
  final int value;
  final IconData icon;

  @override
  Widget build(BuildContext context) => Card(
    margin: const EdgeInsets.only(right: 8),
    child: SizedBox(
      width: 160,
      child: Padding(
        padding: const EdgeInsets.all(12),
        child: Row(
          children: [
            Icon(icon, color: Theme.of(context).colorScheme.primary),
            const SizedBox(width: 8),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text('$value', style: Theme.of(context).textTheme.titleLarge),
                  Text(
                    label,
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                    style: Theme.of(context).textTheme.labelMedium,
                  ),
                ],
              ),
            ),
          ],
        ),
      ),
    ),
  );
}

class _Filtros extends StatelessWidget {
  const _Filtros({
    required this.consulta,
    required this.filters,
    required this.sources,
    required this.onSearch,
    required this.onChange,
  });

  final TextEditingController consulta;
  final FiltrosSubvencionesAdmin filters;
  final List<String> sources;
  final ValueChanged<String> onSearch;
  final ValueChanged<FiltrosSubvencionesAdmin> onChange;

  @override
  Widget build(BuildContext context) => Padding(
    padding: const EdgeInsets.fromLTRB(12, 8, 12, 8),
    child: LayoutBuilder(
      builder: (context, constraints) {
        final wide = constraints.maxWidth >= 760;
        final children = [
          SizedBox(
            width: wide ? 330 : double.infinity,
            child: TextField(
              key: const Key('admin-subvenciones-buscar'),
              controller: consulta,
              onChanged: onSearch,
              decoration: const InputDecoration(
                labelText: 'Buscar título, organismo o referencia',
                prefixIcon: Icon(Icons.search),
                isDense: true,
              ),
            ),
          ),
          _Selector(
            key: ValueKey('estado-${filters.estado}'),
            label: 'Estado',
            value: filters.estado,
            items: const {
              'en_vigor': 'En vigor',
              'finalizadas': 'Finalizadas',
              'todas': 'Todas',
            },
            onChanged: (value) =>
                onChange(filters.copyWith(estado: value, pagina: 0)),
          ),
          _Selector(
            key: ValueKey('visibilidad-${filters.visibilidad}'),
            label: 'Visibilidad',
            value: filters.visibilidad,
            items: const {
              'visibles': 'Visibles',
              'ocultas': 'Ocultas',
              'todas': 'Todas',
            },
            onChanged: (value) =>
                onChange(filters.copyWith(visibilidad: value, pagina: 0)),
          ),
          _Selector(
            key: ValueKey('fuente-${filters.fuente}'),
            label: 'Fuente',
            value: filters.fuente,
            items: {
              for (final source in sources)
                source: source.isEmpty ? 'Todas' : source,
            },
            onChanged: (value) =>
                onChange(filters.copyWith(fuente: value, pagina: 0)),
          ),
        ];
        if (wide) {
          return Row(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              children.first,
              const SizedBox(width: 8),
              ...children
                  .skip(1)
                  .expand(
                    (item) => [Expanded(child: item), const SizedBox(width: 8)],
                  ),
            ],
          );
        }
        return Column(
          children: [
            children.first,
            const SizedBox(height: 8),
            Row(
              children: [
                Expanded(child: children[1]),
                const SizedBox(width: 8),
                Expanded(child: children[2]),
              ],
            ),
            const SizedBox(height: 8),
            children[3],
          ],
        );
      },
    ),
  );
}

class _Selector extends StatelessWidget {
  const _Selector({
    super.key,
    required this.label,
    required this.value,
    required this.items,
    required this.onChanged,
  });
  final String label;
  final String value;
  final Map<String, String> items;
  final ValueChanged<String> onChanged;

  @override
  Widget build(BuildContext context) => DropdownButtonFormField<String>(
    initialValue: value,
    isExpanded: true,
    decoration: InputDecoration(labelText: label, isDense: true),
    items: items.entries
        .map(
          (item) => DropdownMenuItem(value: item.key, child: Text(item.value)),
        )
        .toList(),
    onChanged: (next) {
      if (next != null) onChanged(next);
    },
  );
}

class _Listado extends StatelessWidget {
  const _Listado({
    required this.data,
    required this.filters,
    required this.onChangePage,
    required this.onEdit,
  });
  final ListaSubvenciones data;
  final FiltrosSubvencionesAdmin filters;
  final ValueChanged<int> onChangePage;
  final Future<void> Function(Subvencion item, {bool? visible, bool? revisada})
  onEdit;

  @override
  Widget build(BuildContext context) {
    if (data.elementos.isEmpty) {
      return const Center(child: Text('No hay ayudas con estos filtros.'));
    }
    final first = filters.pagina * 50 + 1;
    final last = (first + data.elementos.length - 1).clamp(0, data.total);
    final hasNext = filters.pagina * 50 + data.elementos.length < data.total;
    return Column(
      children: [
        Padding(
          padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 4),
          child: Row(
            children: [
              Text('${data.total} ayudas · mostrando $first-$last'),
              const Spacer(),
              IconButton(
                tooltip: 'Página anterior',
                onPressed: filters.pagina > 0
                    ? () => onChangePage(filters.pagina - 1)
                    : null,
                icon: const Icon(Icons.chevron_left),
              ),
              Text('${filters.pagina + 1}'),
              IconButton(
                tooltip: 'Página siguiente',
                onPressed: hasNext
                    ? () => onChangePage(filters.pagina + 1)
                    : null,
                icon: const Icon(Icons.chevron_right),
              ),
            ],
          ),
        ),
        Expanded(
          child: ListView.builder(
            itemCount: data.elementos.length,
            itemBuilder: (context, index) {
              final item = data.elementos[index];
              return Card(
                margin: const EdgeInsets.symmetric(horizontal: 12, vertical: 5),
                child: ListTile(
                  key: Key('admin-subvencion-${item.codigo}'),
                  onTap: () => context.push(
                    '/admin/subvenciones/${Uri.encodeComponent(item.codigo)}',
                  ),
                  title: Text(
                    item.titulo,
                    style: item.visible
                        ? null
                        : TextStyle(
                            color: Theme.of(context).colorScheme.outline,
                            decoration: TextDecoration.lineThrough,
                          ),
                  ),
                  subtitle: Text(
                    '${item.fuente} · ${item.ambito}'
                    '${item.fechaFin == null ? '' : ' · fin ${_fecha(item.fechaFin!)}'}',
                  ),
                  leading: Icon(
                    item.revisada
                        ? Icons.fact_check
                        : Icons.pending_actions_outlined,
                    color: item.revisada ? Colors.green : null,
                  ),
                  trailing: PopupMenuButton<String>(
                    onSelected: (action) {
                      if (action == 'visible') {
                        onEdit(item, visible: !item.visible);
                      } else if (action == 'revisada') {
                        onEdit(item, revisada: !item.revisada);
                      }
                    },
                    itemBuilder: (_) => [
                      PopupMenuItem(
                        value: 'revisada',
                        child: Text(
                          item.revisada
                              ? 'Marcar como pendiente'
                              : 'Marcar como revisada',
                        ),
                      ),
                      PopupMenuItem(
                        value: 'visible',
                        child: Text(item.visible ? 'Ocultar' : 'Mostrar'),
                      ),
                    ],
                  ),
                ),
              );
            },
          ),
        ),
      ],
    );
  }
}

class _AvisoError extends StatelessWidget {
  const _AvisoError({required this.mensaje, required this.onRetry});
  final String mensaje;
  final VoidCallback onRetry;

  @override
  Widget build(BuildContext context) => Padding(
    padding: const EdgeInsets.all(16),
    child: Column(
      mainAxisSize: MainAxisSize.min,
      children: [
        Text(mensaje, textAlign: TextAlign.center),
        TextButton(onPressed: onRetry, child: const Text('Reintentar')),
      ],
    ),
  );
}

String _fecha(DateTime value) =>
    '${value.day.toString().padLeft(2, '0')}/'
    '${value.month.toString().padLeft(2, '0')}/${value.year}';
