import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../auth/presentation/auth_controller.dart';
import 'messaging_providers.dart';

class ClientsScreen extends ConsumerStatefulWidget {
  const ClientsScreen({super.key});

  @override
  ConsumerState<ClientsScreen> createState() => _ClientsScreenState();
}

class _ClientsScreenState extends ConsumerState<ClientsScreen> {
  final _search = TextEditingController();
  String _status = 'all';

  @override
  void dispose() {
    _search.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final profile = ref.watch(sessionProvider).valueOrNull!.profile;
    if (!profile.isAdmin) {
      return const Scaffold(
        body: Center(
          child: Text('Solo el administrador puede gestionar clientes.'),
        ),
      );
    }
    final organizations = ref.watch(clientOrganizationsProvider);
    return Scaffold(
      appBar: AppBar(
        leading: IconButton(
          key: const Key('clients-back-button'),
          tooltip: 'Volver al inicio',
          onPressed: () => context.go('/'),
          icon: const Icon(Icons.arrow_back),
        ),
        title: const Text('Clientes'),
        actions: [
          IconButton(
            key: const Key('clients-invite-button'),
            tooltip: 'Invitar cliente',
            onPressed: () => context.go('/invite-client'),
            icon: const Icon(Icons.person_add_alt_1),
          ),
          IconButton(
            tooltip: 'Actualizar',
            onPressed: () => ref.invalidate(clientOrganizationsProvider),
            icon: const Icon(Icons.refresh),
          ),
        ],
      ),
      body: Column(
        children: [
          Padding(
            padding: const EdgeInsets.fromLTRB(16, 16, 16, 8),
            child: TextField(
              key: const Key('clients-search'),
              controller: _search,
              decoration: const InputDecoration(
                prefixIcon: Icon(Icons.search),
                hintText: 'Buscar por código o nombre',
              ),
              onChanged: (_) => setState(() {}),
            ),
          ),
          SingleChildScrollView(
            scrollDirection: Axis.horizontal,
            padding: const EdgeInsets.symmetric(horizontal: 12),
            child: Row(
              children: [
                for (final item in _filters)
                  Padding(
                    padding: const EdgeInsets.symmetric(horizontal: 3),
                    child: FilterChip(
                      key: Key('clients-filter-${item.$1}'),
                      label: Text(item.$2),
                      selected: _status == item.$1,
                      onSelected: (_) => setState(() => _status = item.$1),
                    ),
                  ),
              ],
            ),
          ),
          const SizedBox(height: 8),
          Expanded(
            child: organizations.when(
              loading: () => const Center(child: CircularProgressIndicator()),
              error: (error, _) => Center(
                child: Text('No se pudieron cargar los clientes: $error'),
              ),
              data: (rows) {
                final query = _search.text.trim().toLowerCase();
                final filtered =
                    rows.where((row) {
                        final matchesStatus =
                            _status == 'all' || row.accessStatus == _status;
                        final matchesSearch =
                            query.isEmpty ||
                            row.companyCode.toLowerCase().contains(query) ||
                            row.name.toLowerCase().contains(query);
                        return matchesStatus && matchesSearch;
                      }).toList()
                      ..sort((a, b) => a.displayName.compareTo(b.displayName));
                if (filtered.isEmpty) {
                  return const Center(
                    child: Text('No hay clientes con estos filtros'),
                  );
                }
                return RefreshIndicator(
                  onRefresh: () async =>
                      ref.invalidate(clientOrganizationsProvider),
                  child: ListView.separated(
                    key: const Key('clients-list'),
                    itemCount: filtered.length,
                    separatorBuilder: (_, _) => const Divider(height: 1),
                    itemBuilder: (context, index) {
                      final row = filtered[index];
                      return ListTile(
                        key: Key('client-${row.companyCode}'),
                        leading: CircleAvatar(
                          child: Text(_initials(row.displayName)),
                        ),
                        title: Text(row.displayName),
                        subtitle: Text(row.companyCode),
                        trailing: Row(
                          mainAxisSize: MainAxisSize.min,
                          children: [
                            ClientStatusBadge(status: row.accessStatus),
                            const SizedBox(width: 4),
                            const Icon(Icons.chevron_right),
                          ],
                        ),
                        onTap: () => context.go('/clients/${row.companyCode}'),
                      );
                    },
                  ),
                );
              },
            ),
          ),
        ],
      ),
    );
  }
}

const _filters = <(String, String)>[
  ('all', 'Todos'),
  ('active', 'Activos'),
  ('pending', 'Pendientes'),
  ('not_invited', 'Sin invitar'),
  ('disabled', 'Inactivos'),
  ('invitation_expired', 'Invitación caducada'),
];

class ClientStatusBadge extends StatelessWidget {
  const ClientStatusBadge({super.key, required this.status});

  final String status;

  @override
  Widget build(BuildContext context) {
    final (label, color) = switch (status) {
      'active' => ('Activo', Colors.green),
      'pending' => ('Pendiente de aceptar', Colors.orange),
      'disabled' => ('Inactivo', Colors.red),
      'invitation_expired' => ('Invitación caducada', Colors.deepOrange),
      _ => ('Sin invitar', Colors.grey),
    };
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
      decoration: BoxDecoration(
        color: color.withValues(alpha: 0.12),
        borderRadius: BorderRadius.circular(14),
        border: Border.all(color: color.withValues(alpha: 0.4)),
      ),
      child: Text(
        label,
        style: TextStyle(
          color: color,
          fontSize: 11,
          fontWeight: FontWeight.w700,
        ),
      ),
    );
  }
}

String _initials(String value) => value
    .trim()
    .split(RegExp(r'\s+'))
    .where((part) => part.isNotEmpty)
    .take(2)
    .map((part) => part[0].toUpperCase())
    .join();
