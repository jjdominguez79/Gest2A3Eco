import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../../core/api/api_client.dart';
import '../../../core/validation/email_validation.dart';
import '../../auth/presentation/auth_controller.dart';
import '../domain/client_organization.dart';
import 'messaging_providers.dart';

class ClientsScreen extends ConsumerStatefulWidget {
  const ClientsScreen({super.key});

  @override
  ConsumerState<ClientsScreen> createState() => _ClientsScreenState();
}

class _ClientsScreenState extends ConsumerState<ClientsScreen> {
  final _search = TextEditingController();
  final Set<String> _selected = {};
  String _status = 'all';
  bool _selecting = false;
  bool _bulkSending = false;

  @override
  void dispose() {
    _search.dispose();
    super.dispose();
  }

  String _recipientEmail(ClientOrganization row) => normalizeEmail(
    row.contactEmail.trim().isNotEmpty
        ? row.contactEmail
        : row.organizationEmail,
  );

  bool _canBulkInvite(ClientOrganization row) =>
      row.active &&
      row.accessStatus != 'active' &&
      row.accessStatus != 'disabled' &&
      isValidEmail(_recipientEmail(row));

  String _unavailableReason(ClientOrganization row) {
    if (!row.active) return 'Empresa inactiva';
    if (row.accessStatus == 'active') return 'Acceso ya activo';
    if (row.accessStatus == 'disabled') return 'Acceso deshabilitado';
    if (!isValidEmail(_recipientEmail(row))) return 'Sin correo válido';
    return '';
  }

  void _toggleSelected(ClientOrganization row) {
    if (!_canBulkInvite(row)) {
      final reason = _unavailableReason(row);
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text('No se puede invitar: ${reason.toLowerCase()}.'),
        ),
      );
      return;
    }
    setState(() {
      if (!_selected.add(row.companyCode)) {
        _selected.remove(row.companyCode);
      }
    });
  }

  Future<void> _sendBulk(List<ClientOrganization> rows) async {
    if (rows.isEmpty || _bulkSending) return;
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (dialogContext) => AlertDialog(
        title: const Text('Enviar invitaciones'),
        content: Text(
          'Se enviará una invitación personal y el manual de Gestinem a '
          '${rows.length} ${rows.length == 1 ? 'cliente' : 'clientes'}.',
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(dialogContext, false),
            child: const Text('Cancelar'),
          ),
          FilledButton(
            key: const Key('clients-confirm-bulk-invite'),
            onPressed: () => Navigator.pop(dialogContext, true),
            child: const Text('Enviar'),
          ),
        ],
      ),
    );
    if (confirmed != true || !mounted) return;

    setState(() => _bulkSending = true);
    try {
      final result = await ref
          .read(messagingRepositoryProvider)
          .inviteClients(rows);
      ref.invalidate(clientOrganizationsProvider);
      ref.invalidate(organizationsProvider);
      if (!mounted) return;
      final queued = result['email_queued_count'] as int? ?? 0;
      setState(() {
        _selected.clear();
        _selecting = false;
      });
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text(
            queued == rows.length
                ? 'Se han preparado $queued invitaciones con el manual adjunto.'
                : 'Invitaciones creadas: ${rows.length}. Correos preparados: $queued.',
          ),
        ),
      );
    } catch (error) {
      if (mounted) {
        ScaffoldMessenger.of(
          context,
        ).showSnackBar(SnackBar(content: Text(apiErrorMessage(error))));
      }
    } finally {
      if (mounted) setState(() => _bulkSending = false);
    }
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
        title: Text(
          _selecting ? '${_selected.length} seleccionados' : 'Clientes',
        ),
        actions: [
          if (_selecting)
            IconButton(
              key: const Key('clients-cancel-selection'),
              tooltip: 'Cancelar selección',
              onPressed: () => setState(() {
                _selected.clear();
                _selecting = false;
              }),
              icon: const Icon(Icons.close),
            )
          else ...[
            IconButton(
              key: const Key('clients-bulk-invite-button'),
              tooltip: 'Invitar varios clientes',
              onPressed: () => setState(() => _selecting = true),
              icon: const Icon(Icons.playlist_add_check),
            ),
            IconButton(
              key: const Key('clients-invite-button'),
              tooltip: 'Invitar cliente',
              onPressed: () => context.go('/invite-client'),
              icon: const Icon(Icons.person_add_alt_1),
            ),
          ],
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
                final selectable = filtered.where(_canBulkInvite).toList();
                final selectedRows = rows
                    .where((row) => _selected.contains(row.companyCode))
                    .toList(growable: false);
                if (filtered.isEmpty) {
                  return const Center(
                    child: Text('No hay clientes con estos filtros'),
                  );
                }
                return Column(
                  children: [
                    if (_selecting)
                      Material(
                        color: Theme.of(context).colorScheme.surfaceContainer,
                        child: Padding(
                          padding: const EdgeInsets.symmetric(
                            horizontal: 16,
                            vertical: 8,
                          ),
                          child: Row(
                            children: [
                              TextButton(
                                key: const Key('clients-select-visible'),
                                onPressed: selectable.isEmpty
                                    ? null
                                    : () => setState(
                                        () => _selected.addAll(
                                          selectable.map(
                                            (row) => row.companyCode,
                                          ),
                                        ),
                                      ),
                                child: const Text('Seleccionar visibles'),
                              ),
                              const Spacer(),
                              FilledButton.icon(
                                key: const Key('clients-send-bulk-invite'),
                                onPressed: selectedRows.isEmpty || _bulkSending
                                    ? null
                                    : () => _sendBulk(selectedRows),
                                icon: _bulkSending
                                    ? const SizedBox.square(
                                        dimension: 16,
                                        child: CircularProgressIndicator(
                                          strokeWidth: 2,
                                        ),
                                      )
                                    : const Icon(Icons.send_outlined),
                                label: Text('Enviar (${selectedRows.length})'),
                              ),
                            ],
                          ),
                        ),
                      ),
                    Expanded(
                      child: RefreshIndicator(
                        onRefresh: () async =>
                            ref.invalidate(clientOrganizationsProvider),
                        child: ListView.separated(
                          key: const Key('clients-list'),
                          padding: EdgeInsets.only(
                            bottom: MediaQuery.viewPaddingOf(context).bottom,
                          ),
                          itemCount: filtered.length,
                          separatorBuilder: (_, _) => const Divider(height: 1),
                          itemBuilder: (context, index) {
                            final row = filtered[index];
                            final canInvite = _canBulkInvite(row);
                            final unavailableReason = _unavailableReason(row);
                            return ListTile(
                              key: Key('client-${row.companyCode}'),
                              enabled: !_selecting || canInvite,
                              leading: _selecting
                                  ? Checkbox(
                                      key: Key(
                                        'client-select-${row.companyCode}',
                                      ),
                                      value: _selected.contains(
                                        row.companyCode,
                                      ),
                                      onChanged: canInvite
                                          ? (_) => _toggleSelected(row)
                                          : null,
                                    )
                                  : CircleAvatar(
                                      child: Text(_initials(row.displayName)),
                                    ),
                              title: Text(row.displayName),
                              subtitle: Text(
                                _selecting && !canInvite
                                    ? '${row.companyCode} · $unavailableReason'
                                    : row.companyCode,
                              ),
                              trailing: _selecting
                                  ? null
                                  : Row(
                                      mainAxisSize: MainAxisSize.min,
                                      children: [
                                        ClientStatusBadge(
                                          status: row.accessStatus,
                                        ),
                                        const SizedBox(width: 4),
                                        const Icon(Icons.chevron_right),
                                      ],
                                    ),
                              onTap: _selecting
                                  ? () => _toggleSelected(row)
                                  : () => context.go(
                                      '/clients/${row.companyCode}',
                                    ),
                            );
                          },
                        ),
                      ),
                    ),
                  ],
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
