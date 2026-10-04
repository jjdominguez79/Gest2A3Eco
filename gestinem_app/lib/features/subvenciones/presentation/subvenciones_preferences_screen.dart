import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../core/api/api_client.dart';
import '../domain/subvencion.dart';
import 'subvenciones_providers.dart';

class SubvencionesPreferencesScreen extends ConsumerStatefulWidget {
  const SubvencionesPreferencesScreen({super.key});

  @override
  ConsumerState<SubvencionesPreferencesScreen> createState() =>
      _SubvencionesPreferencesScreenState();
}

class _SubvencionesPreferencesScreenState
    extends ConsumerState<SubvencionesPreferencesScreen> {
  bool _inicializada = false;
  bool _notificaciones = false;
  bool _nacionales = true;
  bool _territorioEmpresa = true;
  bool _guardando = false;
  Map<String, dynamic> _empresa = const {};
  final Map<String, TerritorioSubvencion> _seleccion = {};
  final _consulta = TextEditingController();
  Timer? _debounce;

  @override
  void dispose() {
    _debounce?.cancel();
    _consulta.dispose();
    super.dispose();
  }

  void _buscarTerritorio(String value) {
    setState(() {});
    _debounce?.cancel();
    _debounce = Timer(const Duration(milliseconds: 300), () {
      ref.read(territoriosConsultaProvider.notifier).state = value;
    });
  }

  void _inicializar(PreferenciasSubvenciones value) {
    if (_inicializada) return;
    _inicializada = true;
    _notificaciones = value.notificacionesActivas;
    _nacionales = value.incluirNacionales;
    _territorioEmpresa = value.usarTerritorioEmpresa;
    _empresa = value.territorioEmpresa;
    _seleccion.addEntries(value.suscripciones.map((e) => MapEntry(e.clave, e)));
  }

  Future<void> _guardar() async {
    setState(() => _guardando = true);
    try {
      await ref
          .read(subvencionesRepositoryProvider)
          .guardarPreferencias(
            notificacionesActivas: _notificaciones,
            incluirNacionales: _nacionales,
            usarTerritorioEmpresa: _territorioEmpresa,
            suscripciones: _seleccion.values.toList(),
          );
      ref.invalidate(preferenciasSubvencionesProvider);
      ref.invalidate(subvencionesProvider);
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(content: Text('Preferencias guardadas.')),
        );
        Navigator.of(context).pop();
      }
    } catch (error) {
      if (mounted) {
        ScaffoldMessenger.of(
          context,
        ).showSnackBar(SnackBar(content: Text(apiErrorMessage(error))));
      }
    } finally {
      if (mounted) setState(() => _guardando = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final preferences = ref.watch(preferenciasSubvencionesProvider);
    final territories = ref.watch(territoriosSubvencionesProvider);
    return Scaffold(
      appBar: AppBar(
        title: const Text('Preferencias de ayudas'),
        actions: [
          TextButton(
            key: const Key('guardar-preferencias-subvenciones'),
            onPressed: _guardando || !_inicializada ? null : _guardar,
            child: _guardando
                ? const SizedBox.square(
                    dimension: 20,
                    child: CircularProgressIndicator(strokeWidth: 2),
                  )
                : const Text('Guardar'),
          ),
        ],
      ),
      body: preferences.when(
        loading: () => const Center(child: CircularProgressIndicator()),
        error: (error, _) => Center(child: Text(apiErrorMessage(error))),
        data: (value) {
          _inicializar(value);
          return ListView(
            padding: const EdgeInsets.fromLTRB(12, 8, 12, 28),
            children: [
              SwitchListTile(
                key: const Key('avisos-subvenciones'),
                value: _notificaciones,
                onChanged: (v) => setState(() => _notificaciones = v),
                secondary: const Icon(Icons.notifications_active_outlined),
                title: const Text('Avisarme de nuevas ayudas'),
                subtitle: const Text(
                  'Recibirás una notificación cuando aparezca una convocatoria que coincida.',
                ),
              ),
              const Divider(),
              SwitchListTile(
                value: _nacionales,
                onChanged: (v) => setState(() => _nacionales = v),
                secondary: const Icon(Icons.flag_outlined),
                title: const Text('Toda España'),
                subtitle: const Text('Incluir ayudas de alcance nacional.'),
              ),
              SwitchListTile(
                value: _territorioEmpresa,
                onChanged: (v) => setState(() => _territorioEmpresa = v),
                secondary: const Icon(Icons.business_outlined),
                title: const Text('Territorio de mi empresa'),
                subtitle: Text(_descripcionEmpresa()),
              ),
              const Padding(
                padding: EdgeInsets.fromLTRB(16, 20, 16, 6),
                child: Text(
                  'Otros ámbitos territoriales',
                  style: TextStyle(fontWeight: FontWeight.w700, fontSize: 16),
                ),
              ),
              const Padding(
                padding: EdgeInsets.symmetric(horizontal: 16),
                child: Text(
                  'Puedes seguir tantas comunidades, provincias y municipios como necesites.',
                ),
              ),
              if (_seleccion.isNotEmpty)
                Padding(
                  padding: const EdgeInsets.fromLTRB(16, 12, 16, 0),
                  child: Wrap(
                    spacing: 6,
                    runSpacing: 6,
                    children: _seleccion.values
                        .map(
                          (item) => InputChip(
                            label: Text(item.nombre),
                            onDeleted: () =>
                                setState(() => _seleccion.remove(item.clave)),
                          ),
                        )
                        .toList(),
                  ),
                ),
              Padding(
                padding: const EdgeInsets.fromLTRB(16, 12, 16, 8),
                child: TextField(
                  controller: _consulta,
                  onChanged: _buscarTerritorio,
                  decoration: const InputDecoration(
                    prefixIcon: Icon(Icons.search),
                    hintText: 'Buscar territorio',
                    border: OutlineInputBorder(),
                  ),
                ),
              ),
              territories.when(
                loading: () => const Padding(
                  padding: EdgeInsets.all(24),
                  child: Center(child: CircularProgressIndicator()),
                ),
                error: (error, _) => Padding(
                  padding: const EdgeInsets.all(16),
                  child: Text(apiErrorMessage(error)),
                ),
                data: (items) => _Territorios(
                  items: items,
                  consulta: _consulta.text,
                  seleccion: _seleccion,
                  onChanged: (item, selected) {
                    setState(() {
                      if (selected) {
                        _seleccion[item.clave] = item;
                      } else {
                        _seleccion.remove(item.clave);
                      }
                    });
                  },
                ),
              ),
            ],
          );
        },
      ),
    );
  }

  String _descripcionEmpresa() {
    final parts = [
      _empresa['municipio'],
      _empresa['provincia_nombre'],
      _empresa['ccaa_nombre'],
    ].where((e) => (e?.toString() ?? '').isNotEmpty).map((e) => e.toString());
    final text = parts.join(' · ');
    return text.isEmpty ? 'Usar la dirección registrada de la empresa.' : text;
  }
}

class _Territorios extends StatelessWidget {
  const _Territorios({
    required this.items,
    required this.consulta,
    required this.seleccion,
    required this.onChanged,
  });
  final List<TerritorioSubvencion> items;
  final String consulta;
  final Map<String, TerritorioSubvencion> seleccion;
  final void Function(TerritorioSubvencion, bool) onChanged;

  @override
  Widget build(BuildContext context) {
    final needle = consulta.trim().toLowerCase();
    final visible = items
        .where((e) => needle.isEmpty || e.nombre.toLowerCase().contains(needle))
        .take(100)
        .toList();
    if (visible.isEmpty) {
      return const Padding(
        padding: EdgeInsets.all(20),
        child: Center(child: Text('No se encontraron territorios.')),
      );
    }
    return Column(
      children: visible
          .map(
            (item) => CheckboxListTile(
              key: Key('territorio-${item.clave}'),
              value: seleccion.containsKey(item.clave),
              onChanged: (v) => onChanged(item, v ?? false),
              title: Text(item.nombre),
              subtitle: Text(_nombreNivel(item.nivel)),
              controlAffinity: ListTileControlAffinity.leading,
            ),
          )
          .toList(),
    );
  }

  String _nombreNivel(String value) => switch (value) {
    'AUTONOMICA' => 'Comunidad autónoma',
    'PROVINCIAL' => 'Provincia',
    'MUNICIPAL' => 'Municipio',
    _ => value,
  };
}
