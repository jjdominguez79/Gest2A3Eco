import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../../core/api/api_client.dart';
import '../domain/subvencion.dart';
import 'subvenciones_providers.dart';

class SubvencionesScreen extends ConsumerStatefulWidget {
  const SubvencionesScreen({super.key});

  @override
  ConsumerState<SubvencionesScreen> createState() => _SubvencionesScreenState();
}

class _SubvencionesScreenState extends ConsumerState<SubvencionesScreen> {
  final _consulta = TextEditingController();
  Timer? _debounce;
  final List<Subvencion> _adicionales = [];
  int _pagina = 0;
  bool _cargandoMas = false;

  @override
  void dispose() {
    _debounce?.cancel();
    _consulta.dispose();
    super.dispose();
  }

  void _buscar(String value) {
    _debounce?.cancel();
    _debounce = Timer(const Duration(milliseconds: 350), () {
      if (!mounted) return;
      setState(() {
        _pagina = 0;
        _adicionales.clear();
      });
      ref.read(subvencionesConsultaProvider.notifier).state = value;
    });
  }

  Future<void> _cargarMas(bool paraMi) async {
    if (_cargandoMas) return;
    setState(() => _cargandoMas = true);
    final consulta = ref.read(subvencionesConsultaProvider);
    try {
      final next = await ref
          .read(subvencionesRepositoryProvider)
          .listar(paraMi: paraMi, consulta: consulta, pagina: _pagina + 1);
      if (!mounted) return;
      if (ref.read(subvencionesParaMiProvider) != paraMi ||
          ref.read(subvencionesConsultaProvider) != consulta) {
        return;
      }
      setState(() {
        _pagina += 1;
        _adicionales.addAll(next.elementos);
      });
    } catch (error) {
      if (mounted) {
        ScaffoldMessenger.of(
          context,
        ).showSnackBar(SnackBar(content: Text(apiErrorMessage(error))));
      }
    } finally {
      if (mounted) setState(() => _cargandoMas = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final paraMi = ref.watch(subvencionesParaMiProvider);
    final resultado = ref.watch(subvencionesProvider);
    return Scaffold(
      appBar: AppBar(
        title: const Text('Ayudas y subvenciones'),
        actions: [
          IconButton(
            key: const Key('subvenciones-preferencias'),
            tooltip: 'Preferencias y avisos',
            onPressed: () => context.push('/subvenciones/preferencias'),
            icon: const Icon(Icons.tune),
          ),
        ],
      ),
      body: RefreshIndicator(
        onRefresh: () {
          setState(() {
            _pagina = 0;
            _adicionales.clear();
          });
          return ref.refresh(subvencionesProvider.future);
        },
        child: CustomScrollView(
          physics: const AlwaysScrollableScrollPhysics(),
          slivers: [
            SliverToBoxAdapter(
              child: Padding(
                padding: const EdgeInsets.fromLTRB(16, 16, 16, 8),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.stretch,
                  children: [
                    SegmentedButton<bool>(
                      segments: const [
                        ButtonSegment(
                          value: true,
                          icon: Icon(Icons.auto_awesome_outlined),
                          label: Text('Para ti'),
                        ),
                        ButtonSegment(
                          value: false,
                          icon: Icon(Icons.public),
                          label: Text('Todas'),
                        ),
                      ],
                      selected: {paraMi},
                      onSelectionChanged: (value) {
                        setState(() {
                          _pagina = 0;
                          _adicionales.clear();
                        });
                        ref.read(subvencionesParaMiProvider.notifier).state =
                            value.first;
                      },
                    ),
                    const SizedBox(height: 12),
                    TextField(
                      key: const Key('subvenciones-buscar'),
                      controller: _consulta,
                      onChanged: _buscar,
                      textInputAction: TextInputAction.search,
                      decoration: InputDecoration(
                        hintText: 'Buscar por título',
                        prefixIcon: const Icon(Icons.search),
                        suffixIcon: _consulta.text.isEmpty
                            ? null
                            : IconButton(
                                onPressed: () {
                                  _consulta.clear();
                                  _buscar('');
                                  setState(() {});
                                },
                                icon: const Icon(Icons.clear),
                              ),
                        border: const OutlineInputBorder(),
                      ),
                    ),
                  ],
                ),
              ),
            ),
            resultado.when(
              loading: () => const SliverFillRemaining(
                child: Center(child: CircularProgressIndicator()),
              ),
              error: (error, _) => SliverFillRemaining(
                child: _ErrorAyudas(
                  mensaje: apiErrorMessage(error),
                  onRetry: () => ref.invalidate(subvencionesProvider),
                ),
              ),
              data: (data) {
                final items = [...data.elementos, ..._adicionales];
                if (items.isEmpty) {
                  return SliverFillRemaining(
                    hasScrollBody: false,
                    child: _Vacio(paraMi: paraMi),
                  );
                }
                final hasMore = items.length < data.total;
                return SliverList.builder(
                  itemCount: items.length + 1 + (hasMore ? 1 : 0),
                  itemBuilder: (context, index) {
                    if (index == 0) {
                      return Padding(
                        padding: const EdgeInsets.fromLTRB(18, 4, 18, 2),
                        child: Text(
                          '${data.total} convocatorias vigentes',
                          style: Theme.of(context).textTheme.labelLarge,
                        ),
                      );
                    }
                    if (index > items.length) {
                      return Padding(
                        padding: const EdgeInsets.all(16),
                        child: Center(
                          child: OutlinedButton.icon(
                            onPressed: _cargandoMas
                                ? null
                                : () => _cargarMas(paraMi),
                            icon: _cargandoMas
                                ? const SizedBox.square(
                                    dimension: 18,
                                    child: CircularProgressIndicator(
                                      strokeWidth: 2,
                                    ),
                                  )
                                : const Icon(Icons.expand_more),
                            label: const Text('Cargar más'),
                          ),
                        ),
                      );
                    }
                    return _TarjetaSubvencion(item: items[index - 1]);
                  },
                );
              },
            ),
            const SliverToBoxAdapter(child: SizedBox(height: 24)),
          ],
        ),
      ),
    );
  }
}

class _TarjetaSubvencion extends StatelessWidget {
  const _TarjetaSubvencion({required this.item});
  final Subvencion item;

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    return Card(
      margin: const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
      clipBehavior: Clip.antiAlias,
      child: InkWell(
        key: Key('subvencion-${item.codigo}'),
        onTap: () => context.push('/subvenciones/${item.codigo}'),
        child: Padding(
          padding: const EdgeInsets.all(16),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Row(
                children: [
                  _Ambito(ambito: item.ambito),
                  const Spacer(),
                  if (item.fechaFin != null)
                    Text(
                      'Hasta ${_fecha(item.fechaFin!)}',
                      style: TextStyle(
                        color: scheme.error,
                        fontWeight: FontWeight.w600,
                      ),
                    ),
                ],
              ),
              const SizedBox(height: 10),
              Text(
                item.titulo,
                style: Theme.of(
                  context,
                ).textTheme.titleMedium?.copyWith(fontWeight: FontWeight.w700),
              ),
              if (item.organo.isNotEmpty) ...[
                const SizedBox(height: 6),
                Text(item.organo, style: Theme.of(context).textTheme.bodySmall),
              ],
              if (item.resumenCorto?.isNotEmpty == true) ...[
                const SizedBox(height: 10),
                Text(
                  item.resumenCorto!,
                  maxLines: 3,
                  overflow: TextOverflow.ellipsis,
                ),
              ],
              if (item.etiquetas.isNotEmpty) ...[
                const SizedBox(height: 10),
                Wrap(
                  spacing: 6,
                  runSpacing: 4,
                  children: item.etiquetas
                      .map((e) => Chip(label: Text(e.replaceAll('_', ' '))))
                      .toList(),
                ),
              ],
            ],
          ),
        ),
      ),
    );
  }
}

class _Ambito extends StatelessWidget {
  const _Ambito({required this.ambito});
  final String ambito;

  @override
  Widget build(BuildContext context) => Container(
    padding: const EdgeInsets.symmetric(horizontal: 9, vertical: 4),
    decoration: BoxDecoration(
      color: Theme.of(context).colorScheme.primaryContainer,
      borderRadius: BorderRadius.circular(20),
    ),
    child: Text(
      ambito,
      style: TextStyle(
        color: Theme.of(context).colorScheme.onPrimaryContainer,
        fontSize: 11,
        fontWeight: FontWeight.w700,
      ),
    ),
  );
}

class _Vacio extends StatelessWidget {
  const _Vacio({required this.paraMi});
  final bool paraMi;

  @override
  Widget build(BuildContext context) => Center(
    child: Padding(
      padding: const EdgeInsets.all(32),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          const Icon(Icons.search_off, size: 56),
          const SizedBox(height: 12),
          Text(
            paraMi
                ? 'No hay ayudas vigentes para tus territorios.'
                : 'No hay convocatorias con estos filtros.',
            textAlign: TextAlign.center,
          ),
          if (paraMi) ...[
            const SizedBox(height: 12),
            FilledButton.tonal(
              onPressed: () => context.push('/subvenciones/preferencias'),
              child: const Text('Cambiar territorios'),
            ),
          ],
        ],
      ),
    ),
  );
}

class _ErrorAyudas extends StatelessWidget {
  const _ErrorAyudas({required this.mensaje, required this.onRetry});
  final String mensaje;
  final VoidCallback onRetry;

  @override
  Widget build(BuildContext context) => Center(
    child: Padding(
      padding: const EdgeInsets.all(24),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          Text(mensaje, textAlign: TextAlign.center),
          const SizedBox(height: 12),
          OutlinedButton(onPressed: onRetry, child: const Text('Reintentar')),
        ],
      ),
    ),
  );
}

String _fecha(DateTime value) =>
    '${value.day.toString().padLeft(2, '0')}/${value.month.toString().padLeft(2, '0')}/${value.year}';
